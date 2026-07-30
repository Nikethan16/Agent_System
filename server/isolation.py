"""isolation.py — work on a COPY of a local-mode project, then merge back on human approval.

When a project points at a REAL local folder, editing it in place risks the user's files. With
isolation on (env AGENT_LOCAL_ISOLATED, default ON), the agent instead works on a sandbox COPY:
  * a git repo is cloned locally (so merge-back is a clean, non-destructive branch);
  * a non-git folder is copied.
On approval the changes merge back to the real folder:
  * git repos -> a NEW BRANCH `nikki/<label>` is fetched into the real repo. Nothing in the
    user's working tree changes until THEY merge that branch (full history + one-command undo).
  * non-git folders -> changed files are copied over (the per-turn checkpoint is the undo).

Server-side infra only (never an agent tool); confined to WORKSPACES_DIR + the project's own
validated local path. Takes workspaces_dir as an argument so it never imports db (no cycle).
"""
import os
import shutil
import stat
import subprocess

_ENV = "AGENT_LOCAL_ISOLATED"


def is_enabled() -> bool:
    """Isolated (work-on-a-copy) mode for local projects. OPT-IN for now: set
    AGENT_LOCAL_ISOLATED=1 to turn it on (the agent works on a copy and changes merge back on
    approval). Default OFF = edit the local folder in place (the existing behavior), so enabling
    the feature never silently changes how current projects behave until you choose it."""
    return os.environ.get(_ENV, "0").strip().lower() in ("1", "true", "yes", "on")


def _run(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=180)


def _is_git(path: str) -> bool:
    return os.path.isdir(os.path.join(path, ".git"))


# Nikki's own per-run workspace artifacts — must NEVER be merged into the user's project repo.
_NIKKI_INTERNAL = [".skills/"]


def _exclude_internal(copy: str) -> None:
    """Make the work-copy's git ignore Nikki-internal artifacts (e.g. the .skills/ dir the skills
    system materialises in the workspace), so `git add -A` / `git status` can't sweep them into the
    merge branch or the review diff and pollute the user's repo. Idempotent; git-repos only."""
    exclude = os.path.join(copy, ".git", "info", "exclude")
    try:
        cur = open(exclude, encoding="utf-8").read() if os.path.isfile(exclude) else ""
        add = [p for p in _NIKKI_INTERNAL if p not in cur]
        if add:
            with open(exclude, "a", encoding="utf-8") as f:
                f.write("\n# Nikki internal (auto)\n" + "\n".join(add) + "\n")
    except OSError:
        pass


def _force_rmtree(path: str):
    def _onerr(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_onerr)


def work_copy_path(pid: str, workspaces_dir: str) -> str:
    return os.path.join(workspaces_dir, f"project_{pid}__work")


def ensure_work_copy(pid: str, real_path: str, workspaces_dir: str) -> str:
    """The sandbox work-copy of `real_path`, created on first use. Idempotent — an already
    populated copy is reused (so edits persist across turns, like the normal project workspace)."""
    copy = work_copy_path(pid, workspaces_dir)
    try:
        if os.path.isdir(copy) and os.listdir(copy):
            return copy
        os.makedirs(os.path.dirname(copy), exist_ok=True)
        if _is_git(real_path):
            r = _run(["git", "clone", "--local", "--no-hardlinks", real_path, copy])
            if r.returncode != 0 or not os.path.isdir(copy):
                shutil.copytree(real_path, copy, dirs_exist_ok=True)
        else:
            shutil.copytree(real_path, copy, dirs_exist_ok=True)
        return copy
    except Exception:
        # Never let isolation break a run — fall back to the real path if the copy can't be made.
        return real_path


def has_changes(pid: str, real_path: str, workspaces_dir: str) -> bool:
    copy = work_copy_path(pid, workspaces_dir)
    if not os.path.isdir(copy):
        return False
    if _is_git(copy):
        _exclude_internal(copy)
        return bool(_run(["git", "status", "--porcelain"], cwd=copy).stdout.strip())
    return True


def diff_summary(pid: str, real_path: str, workspaces_dir: str) -> str:
    """A short human summary of what changed on the copy vs the original (git porcelain)."""
    copy = work_copy_path(pid, workspaces_dir)
    if not os.path.isdir(copy):
        return "(no work copy yet)"
    if _is_git(copy):
        _exclude_internal(copy)
        out = _run(["git", "status", "--porcelain"], cwd=copy).stdout.strip()
        return out or "(no changes)"
    return "(non-git folder — changes will be copied over on merge)"


def _slug(label: str) -> str:
    s = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (label or "changes")).strip("-")
    return (s[:40] or "changes").lower()


def merge_to_real(pid: str, real_path: str, workspaces_dir: str, label: str = "") -> dict:
    """Merge the approved work-copy back into the real folder. Git repos land on a new branch
    (non-destructive); non-git folders copy changed files over. Returns {ok, mode, branch, detail}."""
    copy = work_copy_path(pid, workspaces_dir)
    if not os.path.isdir(copy):
        return {"ok": False, "detail": "no work copy to merge"}

    if _is_git(copy) and _is_git(real_path):
        branch = f"nikki/{_slug(label)}"
        # Commit ALL changes (incl. new files) onto a fresh branch in the COPY.
        if _run(["git", "checkout", "-B", branch], cwd=copy).returncode != 0:
            return {"ok": False, "detail": "could not create work branch"}
        _exclude_internal(copy)                    # keep Nikki's .skills/ etc. out of the merge
        _run(["git", "add", "-A"], cwd=copy)
        commit = _run(["git", "-c", "user.email=nikki@local", "-c", "user.name=Nikki",
                       "commit", "-m", f"nikki: {label or 'changes'}"], cwd=copy)
        if commit.returncode != 0 and "nothing to commit" in (commit.stdout + commit.stderr).lower():
            return {"ok": False, "detail": "no changes to merge"}
        # Bring the branch into the REAL repo WITHOUT touching its working tree / current branch.
        fetch = _run(["git", "fetch", copy, f"{branch}:{branch}"], cwd=real_path)
        if fetch.returncode != 0:
            return {"ok": False, "detail": f"fetch into real repo failed: {fetch.stderr[:200]}"}
        return {"ok": True, "mode": "git-branch", "branch": branch,
                "detail": f"Changes landed on branch '{branch}' in your repo. Nothing in your "
                          f"working files changed — review it (git diff {branch}) and merge when ready."}

    # Non-git folder: copy changed files over the original (checkpoint snapshot is the undo).
    try:
        shutil.copytree(copy, real_path, dirs_exist_ok=True)
        return {"ok": True, "mode": "copy", "branch": "",
                "detail": "Changed files copied into your folder (revert via the session checkpoint)."}
    except Exception as e:
        return {"ok": False, "detail": f"copy-merge failed: {type(e).__name__}: {e}"}


def reset_work_copy(pid: str, workspaces_dir: str) -> bool:
    """Discard the work copy (e.g. after a merge, or to start fresh from the real folder)."""
    copy = work_copy_path(pid, workspaces_dir)
    if os.path.isdir(copy):
        _force_rmtree(copy)
        return True
    return False

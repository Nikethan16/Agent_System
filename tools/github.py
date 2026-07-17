"""
github.py — git and GitHub tools for the repo-engineer agent.

All git operations run inside the session workspace (constrained via current_workspace()).
The GitHub token is read from env (GITHUB_TOKEN) and injected into HTTPS URLs for auth;
it is NEVER passed as a tool argument so it can't appear in audit.log or tool schemas.

Register into the toolbelt on import, mirroring the tools/web.py pattern.
Repo contents (READMEs, code, issue text) are untrusted DATA — the repo-engineer
prompt says so; tools here do NOT evaluate any content as instructions.
"""
import os
import re
import subprocess

from core.tools import current_workspace, _safe
from core import toolbelt
from core.boundary import wrap as _wrap_untrusted

_GH_API = "https://api.github.com"


# ---- internal git helpers --------------------------------------------------

def _git(args: list, cwd: str = None, timeout: int = 120) -> tuple:
    """Run a git command in the workspace. Returns (returncode, stdout, stderr)."""
    ws = cwd or current_workspace()
    env = os.environ.copy()
    # Never let git discover a repository ABOVE the workspace. Session workspaces live
    # inside the app's own checkout on the server (data/workspaces/...), so without a
    # ceiling, `git log/status` in a not-yet-cloned workspace silently walks up and
    # operates on the APPLICATION'S repo (live e2e returned the app's own last commit
    # for a question about a cloned repo — and a stray `git commit` would land there).
    env["GIT_CEILING_DIRECTORIES"] = os.path.dirname(os.path.abspath(ws))
    token = env.get("GITHUB_TOKEN", "").strip()
    if token:
        # Use a credential helper via env rather than putting the token on the CLI.
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        env.setdefault("GIT_ASKPASS", "")
    try:
        r = subprocess.run(
            ["git"] + args, cwd=ws,
            capture_output=True, text=True, timeout=timeout, env=env,
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"ERROR: git command timed out after {timeout}s"
    except FileNotFoundError:
        return 1, "", "ERROR: git is not installed or not in PATH"
    except Exception as e:
        return 1, "", f"ERROR: {e}"


def _fmt(rc: int, stdout: str, stderr: str) -> str:
    """Format git output. stdout/stderr are repo-controlled (untrusted DATA)."""
    lines = [f"exit={rc}"]
    if stdout.strip():
        lines.append(_wrap_untrusted(stdout.rstrip(), "git_output"))
    if stderr.strip():
        # stderr is usually git's own messages (clone progress, etc.) — still wrap it
        # because branch names and commit messages inside it are repo-controlled.
        lines.append(_wrap_untrusted(stderr.rstrip(), "git_stderr"))
    return "\n".join(lines)


def _strip_token(s: str, url: str, clean_url: str, token: str = "") -> str:
    """Remove the authenticated URL and bare token from output so credentials
    are never logged, even when git echoes them in a different form."""
    if url != clean_url:
        s = s.replace(url, clean_url)
    if token:
        s = s.replace(token, "***")
    return s


def _auth_url(url: str, token: str) -> str:
    """Return an https URL with `token` injected for password-less auth, FIRST stripping any
    credentials already present so we never double-inject. Double-injection produced
    `https://oauth2:<t>@oauth2:<t>@github.com/...` which git rejects ("Port number...") — the
    bug that made every push fail after a token-authed clone. Non-https URLs and an empty
    token are returned unchanged."""
    if not token or not url.startswith("https://"):
        return url
    bare = re.sub(r"^(https://)[^/@]*@", r"\1", url, count=1)   # drop any user:pass@ already there
    return re.sub(r"^https://", f"https://oauth2:{token}@", bare, count=1)


# ---- server-side clone (project setup, not an agent tool) ------------------
def clone_into(url: str, dest: str, branch: str = "") -> tuple:
    """Clone `url` INTO the existing (empty) directory `dest`. Used when creating a
    project FROM a repo — unlike git_clone (which targets the agent's current workspace),
    this takes an explicit path. Returns (ok: bool, message: str), credentials scrubbed.
    Guards the host against SSRF (private/loopback/metadata) for http(s) URLs."""
    if not url or not url.startswith(("https://", "http://", "git@")):
        return False, "url must start with https://, http://, or git@"
    if url.startswith(("https://", "http://")):
        try:
            from tools.web import _guard_url
            _guard_url(url)                         # block private/loopback/metadata hosts
        except Exception as e:
            return False, f"refused (SSRF guard): {e}"
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    clone_url = url
    if token and url.startswith("https://"):
        clone_url = re.sub(r"^https://", f"https://oauth2:{token}@", url, count=1)
    args = ["clone"]
    if branch:
        args += ["--branch", re.sub(r"[^A-Za-z0-9._/-]", "", branch)[:100]]
    args += [clone_url, "."]                        # into the (empty) dest dir
    rc, stdout, stderr = _git(args, cwd=dest, timeout=300)
    # Don't persist the token in origin's URL (see git_clone) — reset to the clean url so a
    # later git_push single-injects correctly instead of doubling the credentials.
    if rc == 0 and clone_url != url:
        _git(["remote", "set-url", "origin", url], cwd=dest)
    msg = _strip_token((stdout + "\n" + stderr).strip(), clone_url, url, token=token)
    return rc == 0, msg


# ---- public tool functions -------------------------------------------------

def git_clone(url: str, directory: str = "") -> str:
    """Clone a git repository into the workspace. `directory` is an optional subfolder name."""
    if not url or not url.startswith(("https://", "git@", "http://")):
        return "ERROR: url must start with https://, http://, or git@"
    ws = current_workspace()
    token = os.environ.get("GITHUB_TOKEN", "").strip()

    # Inject the token into HTTPS URLs for password-less auth.
    # We never pass the token as a CLI argument — it goes into the URL which is
    # NOT stored in audit.log (the tool arg logged is just `url`, the original).
    clone_url = url
    if token and url.startswith("https://"):
        clone_url = re.sub(r"^https://", f"https://oauth2:{token}@", url, count=1)

    args = ["clone", clone_url]
    if directory:
        # Strip . from allowed set so ".." can never appear in the sanitized name.
        target = re.sub(r"[^a-zA-Z0-9_-]", "_", directory)[:100]
        args.append(target)
        clone_dir = os.path.join(ws, target)
    elif not os.listdir(ws):
        # Empty workspace -> clone INTO it so the repo sits AT the workspace root. Otherwise
        # git makes a subdir and every later tool (which runs in the workspace root) can't see
        # the repo — git_status returns "not a git repository" and the whole clone->edit->push
        # flow breaks. This matches how project repo-mode clones (clone_into with ".").
        args.append(".")
        clone_dir = ws
    else:
        clone_dir = os.path.join(ws, re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1]))

    rc, stdout, stderr = _git(args, cwd=ws)
    # A tokened clone bakes the token into origin's URL. Reset origin to the CLEAN url so
    # (1) the token isn't persisted to .git/config on disk, and (2) a later git_push doesn't
    # re-inject the token on top of it (which produced a malformed oauth2:..@oauth2:..@ URL
    # and made every push after a tool-clone fail).
    if rc == 0 and clone_url != url:
        _git(["remote", "set-url", "origin", url], cwd=clone_dir)
    # Scrub the authenticated URL and bare token from any output before returning.
    stdout = _strip_token(stdout, clone_url, url, token=token)
    stderr = _strip_token(stderr, clone_url, url, token=token)
    return _fmt(rc, stdout, stderr)


def git_status() -> str:
    """Show git status in the workspace."""
    rc, stdout, stderr = _git(["status"])
    return _fmt(rc, stdout, stderr)


def git_diff(path: str = "") -> str:
    """Show git diff for a file or the whole workspace."""
    args = ["diff"]
    if path:
        try:
            safe = _safe(path)
            args.append(safe)
        except ValueError as e:
            return f"ERROR: {e}"
    rc, stdout, stderr = _git(args)
    return _fmt(rc, stdout, stderr)


def git_log(n: int = 10) -> str:
    """Show the last N git commits."""
    rc, stdout, stderr = _git(["log", f"--oneline", f"-{max(1, min(n, 50))}"])
    return _fmt(rc, stdout, stderr)


def git_checkout_branch(branch: str, create: bool = True) -> str:
    """Checkout or create a git branch in the workspace."""
    if not branch or not re.match(r"^[a-zA-Z0-9._/\-]+$", branch):
        return "ERROR: invalid branch name (only alphanumeric, . _ / - allowed)"
    if create:
        rc, stdout, stderr = _git(["checkout", "-b", branch])
        if rc != 0 and "already exists" in stderr:
            rc, stdout, stderr = _git(["checkout", branch])
    else:
        rc, stdout, stderr = _git(["checkout", branch])
    return _fmt(rc, stdout, stderr)


def git_commit(message: str, paths: str = "") -> str:
    """Stage files and create a git commit. `paths` is space-separated workspace-relative paths
    (empty = stage all changes)."""
    if not message or not message.strip():
        return "ERROR: commit message is required"
    add_args = ["add"] + (paths.split() if paths.strip() else ["-A"])
    rc, stdout, stderr = _git(add_args)
    if rc != 0:
        return _fmt(rc, stdout, stderr)
    # Configure a minimal identity if not set (needed in fresh containers)
    _git(["config", "--local", "user.email", "agent@agentcore.local"])
    _git(["config", "--local", "user.name", "Agent Core"])
    rc, stdout, stderr = _git(["commit", "-m", message])
    return _fmt(rc, stdout, stderr)


def git_push(branch: str = "", remote: str = "origin") -> str:
    """Push the current branch to the remote. Uses GITHUB_TOKEN from env for HTTPS auth."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    ws = current_workspace()

    # Get the remote URL and inject the token for auth (never exposes token on CLI)
    rc, remote_url, _ = _git(["remote", "get-url", remote])
    remote_url = remote_url.strip()
    auth_url = _auth_url(remote_url, token)
    if auth_url != remote_url:
        _git(["remote", "set-url", remote, auth_url], cwd=ws)

    try:
        args = ["push", "--set-upstream", remote, branch or "HEAD"]
        rc, stdout, stderr = _git(args)
        stdout = _strip_token(stdout, auth_url, remote_url)
        stderr = _strip_token(stderr, auth_url, remote_url)
        return _fmt(rc, stdout, stderr)
    finally:
        # Restore the original (tokenless) URL
        if auth_url != remote_url:
            _git(["remote", "set-url", remote, remote_url], cwd=ws)


def create_pull_request(title: str, body: str, head_branch: str,
                        base_branch: str = "main", repo: str = "") -> str:
    """Create a GitHub pull request via the REST API.
    `repo` is 'owner/repo'; auto-detected from the origin remote if omitted.
    Requires GITHUB_TOKEN in env."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return "ERROR: GITHUB_TOKEN is not set. Add it to .env to create pull requests."

    if not repo:
        rc, remote_url, _ = _git(["remote", "get-url", "origin"])
        if rc == 0:
            m = re.search(r"github\.com[:/](.+?)(?:\.git)?\s*$", remote_url.strip())
            repo = m.group(1) if m else ""
    if not repo:
        return ("ERROR: could not detect the GitHub repo from the origin remote URL. "
                "Pass 'owner/repo' as the `repo` argument.")

    import httpx
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "title": title,
        "body": body,
        "head": head_branch,
        "base": base_branch,
    }
    try:
        r = httpx.post(f"{_GH_API}/repos/{repo}/pulls",
                       json=payload, headers=headers, timeout=30)
        if r.status_code in (200, 201):
            data = r.json()
            return (f"PR created: {data.get('html_url', '?')} "
                    f"(#{data.get('number', '?')}) — {data.get('title', '')}")
        return f"ERROR {r.status_code}: {r.text[:500]}"
    except Exception as e:
        return f"ERROR creating PR: {e}"


# ---- register into the toolbelt --------------------------------------------
def _obj(props, req=None):
    return {"type": "object", "properties": props, "required": req or []}


_S = "string"

toolbelt.register_fn(
    "git_clone",
    lambda url, directory="": git_clone(url, directory),
    _obj({"url":       {"type": _S, "description": "Repository URL (https:// or git@)"},
          "directory": {"type": _S, "description": "Optional subfolder name inside the workspace"}},
         ["url"]),
    "Clone a git repository into the workspace sandbox.",
    toolbelt.RISK_WRITE,
)
toolbelt.register_fn(
    "git_status",
    lambda: git_status(),
    _obj({}),
    "Show git status in the workspace.",
    toolbelt.RISK_SAFE,
)
toolbelt.register_fn(
    "git_diff",
    lambda path="": git_diff(path),
    _obj({"path": {"type": _S, "description": "File path (optional; empty = whole workspace)"}}),
    "Show git diff for a file or the whole workspace.",
    toolbelt.RISK_SAFE,
)
toolbelt.register_fn(
    "git_log",
    lambda n=10: git_log(n),
    _obj({"n": {"type": "integer", "description": "Number of commits to show (default 10, max 50)"}}),
    "Show recent git commits in the workspace.",
    toolbelt.RISK_SAFE,
)
toolbelt.register_fn(
    "git_checkout_branch",
    lambda branch, create=True: git_checkout_branch(branch, create),
    _obj({"branch": {"type": _S},
          "create": {"type": "boolean",
                     "description": "Create the branch if it doesn't exist (default true)"}},
         ["branch"]),
    "Checkout or create a git branch in the workspace.",
    toolbelt.RISK_WRITE,
)
toolbelt.register_fn(
    "git_commit",
    lambda message, paths="": git_commit(message, paths),
    _obj({"message": {"type": _S},
          "paths":   {"type": _S,
                      "description": "Space-separated workspace-relative paths to stage "
                                     "(empty = stage all changes)"}},
         ["message"]),
    "Stage files and create a git commit in the workspace.",
    toolbelt.RISK_WRITE,
)
toolbelt.register_fn(
    "git_push",
    lambda branch="", remote="origin": git_push(branch, remote),
    _obj({"branch": {"type": _S, "description": "Branch to push (default: current HEAD)"},
          "remote": {"type": _S, "description": "Remote name (default: origin)"}}),
    "Push the current branch to the remote. Requires GITHUB_TOKEN in env.",
    toolbelt.RISK_CRITICAL,
    requires_human=True,
)
toolbelt.register_fn(
    "create_pull_request",
    lambda title, body, head_branch, base_branch="main", repo="": create_pull_request(
        title, body, head_branch, base_branch, repo),
    _obj({"title":       {"type": _S},
          "body":        {"type": _S, "description": "PR description (markdown)"},
          "head_branch": {"type": _S, "description": "Branch containing the changes"},
          "base_branch": {"type": _S, "description": "Target branch (default: main)"},
          "repo":        {"type": _S, "description": "owner/repo (auto-detected from origin if omitted)"}},
         ["title", "body", "head_branch"]),
    "Create a GitHub pull request via the REST API. Requires GITHUB_TOKEN.",
    toolbelt.RISK_CRITICAL,
    requires_human=True,
)

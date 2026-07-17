"""
localmode.py — the gate for LOCAL-FOLDER projects (edit real files on the machine).

This deliberately lets a project's workspace be a real directory on the host instead of
the sandboxed data/workspaces/… copy — the desktop workflow (edit local → test → push).
Because it pierces the workspace sandbox, it is OFF unless explicitly enabled, and even
then confined to a root:

  * AGENT_LOCAL_MODE=1        turns the feature on. The public VM never sets it, so a
                             logged-in user there can NEVER create a local-folder project.
  * AGENT_LOCAL_ROOT=<dir>   the only tree a local project may live under (default: the
                             user's home). Paths are realpath-resolved (no symlink escape)
                             and must be inside this root — so nobody can point at / or
                             C:\\Windows even with the feature on.

Nothing here imports db/projects, so db can consult it while resolving a workspace path.
"""
import os


def enabled() -> bool:
    return os.environ.get("AGENT_LOCAL_MODE", "").strip().lower() in ("1", "true", "yes")


def allowed_root() -> str:
    root = os.environ.get("AGENT_LOCAL_ROOT", "").strip() or os.path.expanduser("~")
    return os.path.realpath(os.path.expanduser(root))


def validate_path(path: str):
    """Return (ok, resolved_absolute_path) on success, else (False, error_message).
    Enforces: feature enabled · non-empty · resolves INSIDE allowed_root() · is a dir."""
    if not enabled():
        return False, "local mode is disabled (set AGENT_LOCAL_MODE=1 on a local run)"
    p = (path or "").strip()
    if not p:
        return False, "a folder path is required"
    real = os.path.realpath(os.path.expanduser(p))
    root = allowed_root()
    if not (real == root or real.startswith(root + os.sep)):
        return False, f"path must be inside {root} (set AGENT_LOCAL_ROOT to widen)"
    if not os.path.isdir(real):
        return False, "path is not an existing directory"
    return True, real


def browse(path: str = ""):
    """List the immediate subfolders of `path` (default: allowed_root) for the UI folder
    picker. Confined to allowed_root() — a path above/outside it snaps back to the root, so
    the picker can never navigate to / or C:\\Windows. Returns (ok, payload|error) where
    payload = {root, path, parent, dirs:[{name, path, is_repo}]}."""
    if not enabled():
        return False, "local mode is disabled (set AGENT_LOCAL_MODE=1 on a local run)"
    root = allowed_root()
    p = (path or "").strip()
    real = os.path.realpath(os.path.expanduser(p)) if p else root
    if not (real == root or real.startswith(root + os.sep)):
        real = root                          # outside the allowed tree -> snap back to root
    if not os.path.isdir(real):
        return False, "not a directory"
    dirs = []
    try:
        for name in sorted(os.listdir(real), key=str.lower):
            if name.startswith("."):         # hide dotfolders (noise); repos still detected below
                continue
            full = os.path.join(real, name)
            if not os.path.isdir(full):
                continue
            dirs.append({"name": name, "path": full,
                         "is_repo": os.path.isdir(os.path.join(full, ".git"))})
    except PermissionError:
        return False, "permission denied"
    return True, {"root": root, "path": real,
                  "parent": "" if real == root else os.path.dirname(real), "dirs": dirs}

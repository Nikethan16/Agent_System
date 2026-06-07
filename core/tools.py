"""
tools.py — the agent's hands. Plain functions + their OpenAI-format schemas.

All file/shell access is confined to a WORKSPACE directory so an agent can't
touch the rest of the disk. For real production, run run_bash inside a
container/VM, not just a chroot-style path check.
"""
import os
import difflib
import contextvars
import subprocess

# Default sandbox root (env-configurable). Per-session code can override the root
# for the duration of a call via using_workspace(); the containment check below is
# unchanged — tools stay sandboxed, only the *location* of the sandbox is per-session.
WORKSPACE = os.path.abspath(os.environ.get("AGENT_WORKSPACE", "./workspace"))
os.makedirs(WORKSPACE, exist_ok=True)

_ws_override = contextvars.ContextVar("workspace_root", default=None)


def current_workspace() -> str:
    """The active sandbox root: a per-call override if set, else the default."""
    root = _ws_override.get() or WORKSPACE
    os.makedirs(root, exist_ok=True)
    return root


class using_workspace:
    """Context manager: confine tools to `root` for the duration of the block."""
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self._token = None

    def __enter__(self):
        os.makedirs(self.root, exist_ok=True)
        self._token = _ws_override.set(self.root)
        return self.root

    def __exit__(self, *exc):
        _ws_override.reset(self._token)
        return False


def _safe(path: str) -> str:
    """Resolve a path and refuse anything that escapes the (current) workspace."""
    root = current_workspace()
    full = os.path.abspath(os.path.join(root, path))
    if not (full == root or full.startswith(root + os.sep)):
        raise ValueError("path escapes workspace")
    return full


def read_file(path: str) -> str:
    try:
        with open(_safe(path)) as f:
            return f.read()
    except Exception as e:
        return f"ERROR reading {path}: {e}"


def write_file(path: str, content: str) -> str:
    try:
        full = _safe(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(content)
        return f"Wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"ERROR writing {path}: {e}"


def _short_diff(before: str, after: str, max_lines: int = 40) -> str:
    """A compact unified diff the model can read back to confirm its edit landed."""
    lines = list(difflib.unified_diff(
        before.splitlines(), after.splitlines(), lineterm="", n=2))
    body = [ln for ln in lines if not ln.startswith(("---", "+++"))]
    if len(body) > max_lines:
        body = body[:max_lines] + [f"... ({len(body) - max_lines} more diff lines)"]
    return "\n".join(body)


def edit_file(path: str, old_string: str, new_string: str = "",
              replace_all: bool = False) -> str:
    """Surgically replace an exact snippet in an existing file (prefer this over a
    full-file overwrite). old_string must match EXACTLY (incl. whitespace) and be
    unique unless replace_all=True. Returns a small diff so the change is verifiable."""
    try:
        full = _safe(path)
    except ValueError as e:
        return f"ERROR: {e}"
    if not old_string:
        return ("ERROR: old_string must be non-empty. To create a new file use "
                "write_file; to delete text pass the snippet as old_string and \"\" as new_string.")
    if not os.path.isfile(full):
        return f"ERROR editing {path}: file not found (create it with write_file first)."
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            before = f.read()
    except Exception as e:
        return f"ERROR reading {path}: {e}"
    count = before.count(old_string)
    if count == 0:
        return (f"ERROR: old_string not found in {path}. Read the file first and copy the "
                "exact text to replace (including indentation/whitespace).")
    if count > 1 and not replace_all:
        return (f"ERROR: old_string appears {count} times in {path}; it must be unique. "
                "Include more surrounding context to target one spot, or set replace_all=true.")
    after = (before.replace(old_string, new_string) if replace_all
             else before.replace(old_string, new_string, 1))
    if after == before:
        return f"No change: new_string is identical to old_string in {path}."
    try:
        with open(full, "w", encoding="utf-8") as f:
            f.write(after)
    except Exception as e:
        return f"ERROR writing {path}: {e}"
    n = count if replace_all else 1
    diff = _short_diff(before, after)
    return f"Edited {path}: replaced {n} occurrence(s)." + (f"\n{diff}" if diff else "")


def list_files(directory: str = ".") -> str:
    try:
        return "\n".join(sorted(os.listdir(_safe(directory)))) or "(empty)"
    except Exception as e:
        return f"ERROR listing {directory}: {e}"


def run_bash(command: str) -> str:
    # Kill-switch for deployed environments: the cwd "sandbox" is NOT real
    # containment (absolute paths still work), so allow operators to disable shell
    # execution entirely. Set AGENT_DISABLE_BASH=1 in any networked deployment and
    # run shell only inside a real container/VM.
    if os.environ.get("AGENT_DISABLE_BASH", "").strip() in ("1", "true", "yes"):
        return ("ERROR: shell execution is disabled (AGENT_DISABLE_BASH is set). "
                "Run this app's bash tool only inside a container/VM sandbox.")
    try:
        out = subprocess.run(
            command, shell=True, cwd=current_workspace(),
            capture_output=True, text=True, timeout=30,
        )
        return f"exit={out.returncode}\nSTDOUT:\n{out.stdout}\nSTDERR:\n{out.stderr}"
    except subprocess.TimeoutExpired:
        return "ERROR running command: timed out after 30s"
    except Exception as e:
        return f"ERROR running command: {e}"


# OpenAI-format tool schemas (LiteLLM uses this format for every provider).
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a workspace directory (default: root).",
            "parameters": {
                "type": "object",
                "properties": {"directory": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Run a shell command in the workspace (tests, git, "
                           "package installs, executing code).",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_files": list_files,
    "run_bash": run_bash,
}

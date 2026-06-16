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

from . import cache
from .boundary import wrap as _wrap_untrusted

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
            content = f.read()
        return _wrap_untrusted(content, "workspace_file", path=path)
    except Exception as e:
        return f"ERROR reading {path}: {e}"


def parse_document(path: str) -> str:
    """Convert a workspace document (PDF / DOCX / PPTX / XLSX / HTML) to clean markdown
    so an agent can read a spec/FRS with structure (headings, tables) intact — far better
    than raw bytes. Uses markitdown, with a pypdf / plain-text fallback. (C2)"""
    try:
        full = _safe(path)
    except Exception as e:
        return f"ERROR: {e}"
    if not os.path.isfile(full):
        return f"ERROR: no such file: {path}"
    # Cache the parse keyed on path + mtime + size, so a repeated read is instant but a
    # CHANGED file re-parses (no stale content). Parsing PDFs/DOCX is slow, so this helps.
    _pc = cache.get_cache("parse_document")
    try:
        st = os.stat(full)
        ckey = cache.key_for("parse", full, st.st_mtime_ns, st.st_size)
        hit = _pc.get(ckey)
        if hit is not None:
            return hit
    except OSError:
        ckey = None
    try:
        from markitdown import MarkItDown
        md = MarkItDown().convert(full)
        out = (getattr(md, "text_content", None) or str(md))[:20000]
    except Exception as e:
        try:
            if full.lower().endswith(".pdf"):
                from pypdf import PdfReader
                out = "\n".join((p.extract_text() or "") for p in PdfReader(full).pages)[:20000]
            else:
                with open(full, encoding="utf-8", errors="replace") as f:
                    out = f.read(20000)
        except Exception as e2:
            return f"ERROR parsing {path}: {e}; fallback failed: {e2}"
    out = _wrap_untrusted(out, "document_content", path=path)
    if ckey:
        _pc.put(ckey, out)
    return out


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


# Cap each bash stream so verbose output (pip install, pytest -v) can't balloon the
# agent's message history. Keep the HEAD and TAIL — the head shows what started, the
# tail shows the result/error summary, which is what the model needs to act on.
_BASH_OUT_CAP = int(os.environ.get("AGENT_BASH_OUTPUT_CAP", "4000"))


def _clip(s: str) -> str:
    s = s or ""
    if len(s) <= _BASH_OUT_CAP:
        return s
    head = _BASH_OUT_CAP // 2
    tail = _BASH_OUT_CAP - head
    return (f"{s[:head]}\n... [{len(s) - _BASH_OUT_CAP} chars truncated] ...\n{s[-tail:]}")


def run_bash(command: str) -> str:
    if os.environ.get("AGENT_DISABLE_BASH", "").strip() in ("1", "true", "yes"):
        return ("ERROR: shell execution is disabled (AGENT_DISABLE_BASH is set). "
                "Run this app's bash tool only inside a container/VM sandbox.")
    ws = current_workspace()
    image = os.environ.get("AGENT_BASH_DOCKER_IMAGE", "").strip()
    if not image:
        return ("ERROR: AGENT_BASH_DOCKER_IMAGE is not set. "
                "Set it to a Docker image (e.g. python:3.11-slim) to enable safe shell execution. "
                "The host-shell fallback is disabled — it offers no real containment.")

    timeout = int(os.environ.get("AGENT_BASH_DOCKER_TIMEOUT", "120"))
    memory  = os.environ.get("AGENT_BASH_DOCKER_MEMORY", "512m")
    cpus    = os.environ.get("AGENT_BASH_DOCKER_CPUS", "1.0")
    network = os.environ.get("AGENT_BASH_DOCKER_NETWORK", "none")
    pids    = os.environ.get("AGENT_BASH_DOCKER_PIDS", "64")

    import uuid as _uuid_mod
    cid_file = os.path.join(
        os.environ.get("TMPDIR", "/tmp"),
        f"agent_cid_{_uuid_mod.uuid4().hex}"
    )
    argv = [
        "docker", "run", "--rm",
        "--cidfile", cid_file,
        "--network", network,
        "--memory", memory,
        "--cpus", cpus,
        "--pids-limit", pids,
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--read-only",
        "--tmpfs", "/tmp:size=256m",
        "-v", f"{ws}:/ws:rw",
        "-w", "/ws",
        image, "bash", "-lc", command,
    ]
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        # stdout/stderr are program output from the container — untrusted DATA, and
        # potentially huge, so clip each stream before wrapping it in the boundary.
        body = _wrap_untrusted(
            f"STDOUT:\n{_clip(out.stdout)}\nSTDERR:\n{_clip(out.stderr)}",
            "command_output", command=command[:120])
        return f"exit={out.returncode}\n{body}"
    except subprocess.TimeoutExpired:
        try:
            with open(cid_file) as _f:
                cid = _f.read().strip()
            if cid:
                subprocess.run(["docker", "kill", cid], capture_output=True, timeout=10)
        except Exception:
            pass
        return f"ERROR running command: timed out after {timeout}s"
    except FileNotFoundError:
        return "ERROR: docker not found — install Docker and ensure it is in PATH"
    except Exception as e:
        return f"ERROR running command: {e}"
    finally:
        try:
            os.unlink(cid_file)
        except Exception:
            pass


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

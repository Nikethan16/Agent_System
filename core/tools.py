"""
tools.py — the agent's hands. Plain functions + their OpenAI-format schemas.

All file/shell access is confined to a WORKSPACE directory so an agent can't
touch the rest of the disk. For real production, run run_bash inside a
container/VM, not just a chroot-style path check.
"""
import os
import re
import fnmatch
import difflib
import contextvars
import subprocess
from pathlib import Path

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


# Read caps (design inspired by OpenCode tool/read.ts — see THIRD_PARTY.md).
# Keep a single big read from blowing the agent's context window; line numbers
# make the snippets an agent later passes to edit_file far easier to produce.
_READ_MAX_LINES = int(os.environ.get("AGENT_READ_MAX_LINES", "2000"))
_READ_MAX_BYTES = int(os.environ.get("AGENT_READ_MAX_BYTES", str(50 * 1024)))
_READ_MAX_LINE = 2000   # truncate any single very-long line


def read_file(path: str, offset: int = 1, limit: int = None) -> str:
    """Read a file from the workspace, returning numbered lines.

    offset: 1-indexed first line to show (default 1). limit: max lines to return
    (default/cap 2000). Output is capped at ~50KB and individual lines at 2000
    chars; a footer says how to page (offset=N) when there's more. Reading a large
    file in chunks keeps the agent's context lean."""
    try:
        full = _safe(path)
    except ValueError as e:
        return f"ERROR: {e}"
    try:
        with open(full, encoding="utf-8", errors="replace") as f:
            all_lines = f.read().splitlines()
    except Exception as e:
        return f"ERROR reading {path}: {e}"

    total = len(all_lines)
    try:
        offset = max(1, int(offset))
    except (TypeError, ValueError):
        offset = 1
    try:
        limit = _READ_MAX_LINES if limit is None else max(1, int(limit))
    except (TypeError, ValueError):
        limit = _READ_MAX_LINES
    limit = min(limit, _READ_MAX_LINES)

    start = offset - 1
    window = all_lines[start:start + limit]
    out, used, byte_cut = [], 0, False
    for i, ln in enumerate(window):
        if len(ln) > _READ_MAX_LINE:
            ln = ln[:_READ_MAX_LINE] + " …[line truncated]"
        numbered = f"{start + i + 1}: {ln}"
        size = len(numbered.encode("utf-8")) + 1
        if used + size > _READ_MAX_BYTES and out:
            byte_cut = True
            break
        out.append(numbered)
        used += size

    last = start + len(out)
    body = "\n".join(out)
    if total == 0:
        footer = "\n\n(Empty file.)"
    elif byte_cut or last < total:
        footer = (f"\n\n(Showing lines {offset}-{last} of {total}. "
                  f"Use offset={last + 1} to continue.)")
    else:
        footer = f"\n\n(End of file — {total} lines.)"
    return _wrap_untrusted(body + footer, "workspace_file", path=path)


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


# ---------------------------------------------------------------------------
# Fuzzy edit-matching cascade.
#
# DERIVED FROM OpenCode (https://github.com/sst/opencode, MIT, Copyright (c)
# 2025 opencode): packages/opencode/src/tool/edit.ts. This is a Python
# reimplementation of their idea — try progressively looser but BOUNDED match
# strategies so a model's near-miss snippet (off by whitespace/indentation)
# still lands, while refusing to GUESS when no confident, unique match exists.
# See THIRD_PARTY.md.
#
# We keep 5 of OpenCode's 9 strategies. Dropped (with reason): escape-normalized
# (rare, risky), trimmed-boundary (subsumed by line-trimmed), context-aware
# (overlaps block-anchor at a looser 0.50 threshold = more guessing), and
# multi-occurrence (only serves replace_all, handled by our exact path). We also
# raise the block-anchor similarity threshold from OpenCode's 0.65 to 0.85.
# ---------------------------------------------------------------------------

_BLOCK_ANCHOR_THRESHOLD = 0.85   # min middle-line similarity for a block-anchor match


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _exact_replacer(content, old):
    """Strategy 1 — the literal snippet."""
    if old in content:
        yield old


def _line_trimmed_replacer(content, old):
    """Strategy 2 — match a run of lines ignoring each line's leading/trailing
    whitespace (handles a model that re-indented or trimmed the snippet)."""
    c_lines = content.split("\n")
    o_lines = old.split("\n")
    if o_lines and o_lines[-1] == "":
        o_lines = o_lines[:-1]
    if not o_lines:
        return
    o_trim = [ln.strip() for ln in o_lines]
    # precompute character offsets of each content line
    offsets, pos = [], 0
    for ln in c_lines:
        offsets.append(pos)
        pos += len(ln) + 1
    for i in range(len(c_lines) - len(o_lines) + 1):
        if all(c_lines[i + j].strip() == o_trim[j] for j in range(len(o_lines))):
            start = offsets[i]
            end = offsets[i + len(o_lines) - 1] + len(c_lines[i + len(o_lines) - 1])
            yield content[start:end]


def _whitespace_normalized_replacer(content, old):
    """Strategy 3 — match where runs of whitespace differ (e.g. tabs vs spaces,
    a double space vs single). Build a regex: every whitespace run in old becomes
    \\s+, everything else literal."""
    stripped = old.strip()
    if not stripped:
        return
    # Split on whitespace runs, escape each literal token, rejoin with \s+ so any
    # run of whitespace in the file matches (tabs vs spaces, single vs double).
    tokens = [t for t in re.split(r"\s+", stripped) if t]
    if not tokens:
        return
    pattern = r"\s+".join(re.escape(t) for t in tokens)
    try:
        for m in re.finditer(pattern, content):
            yield m.group(0)
    except re.error:
        return


def _indentation_flexible_replacer(content, old):
    """Strategy 4 — strip the common leading indentation from the snippet and
    match lines ignoring leading indentation only (preserves internal spacing)."""
    o_lines = old.split("\n")
    if o_lines and o_lines[-1] == "":
        o_lines = o_lines[:-1]
    if not o_lines:
        return
    o_noindent = [ln.lstrip() for ln in o_lines]
    c_lines = content.split("\n")
    offsets, pos = [], 0
    for ln in c_lines:
        offsets.append(pos)
        pos += len(ln) + 1
    for i in range(len(c_lines) - len(o_lines) + 1):
        if all(c_lines[i + j].lstrip() == o_noindent[j] for j in range(len(o_lines))):
            start = offsets[i]
            end = offsets[i + len(o_lines) - 1] + len(c_lines[i + len(o_lines) - 1])
            yield content[start:end]


def _block_anchor_replacer(content, old):
    """Strategy 5 — for a 3+ line block, anchor on the first and last lines
    (trimmed) and accept a window only if the MIDDLE lines are >= 0.85 similar.
    Refuses to guess below the threshold (no yield)."""
    o_lines = [ln for ln in old.split("\n")]
    if o_lines and o_lines[-1] == "":
        o_lines = o_lines[:-1]
    if len(o_lines) < 3:
        return
    first, last = o_lines[0].strip(), o_lines[-1].strip()
    block_len = len(o_lines)
    c_lines = content.split("\n")
    offsets, pos = [], 0
    for ln in c_lines:
        offsets.append(pos)
        pos += len(ln) + 1
    o_middle = "\n".join(o_lines[1:-1])
    for i in range(len(c_lines) - block_len + 1):
        if c_lines[i].strip() != first or c_lines[i + block_len - 1].strip() != last:
            continue
        c_middle = "\n".join(c_lines[i + 1:i + block_len - 1])
        if _ratio(o_middle, c_middle) >= _BLOCK_ANCHOR_THRESHOLD:
            start = offsets[i]
            end = offsets[i + block_len - 1] + len(c_lines[i + block_len - 1])
            yield content[start:end]


_REPLACERS = (
    _exact_replacer,
    _line_trimmed_replacer,
    _whitespace_normalized_replacer,
    _indentation_flexible_replacer,
    _block_anchor_replacer,
)


def _is_disproportionate(candidate: str, old: str) -> bool:
    """Reject a match whose span is much larger than the snippet — a sign the
    fuzzy matcher latched onto the wrong (too-broad) region."""
    o_lines = old.split("\n")
    c_lines = candidate.split("\n")
    if len(c_lines) >= max(len(o_lines) + 3, len(o_lines) * 2):
        return True
    if len(o_lines) == 1:
        return False
    return len(candidate.strip()) > max(len(old.strip()) + 500, len(old.strip()) * 4)


def _find_match(content: str, old: str, replace_all: bool):
    """Run the cascade. Returns (candidate, count) for the first strategy that
    yields a usable match, or ('AMBIGUOUS', n) when a strategy matched but in
    multiple places (and not replace_all), or (None, 0) when nothing matched."""
    saw_ambiguous = 0
    for replacer in _REPLACERS:
        for candidate in replacer(content, old):
            if not candidate or candidate not in content:
                continue
            if _is_disproportionate(candidate, old):
                continue
            count = content.count(candidate)
            if count == 1 or replace_all:
                return candidate, count
            # matched in >1 place and not replace_all -> ambiguous; keep looking
            saw_ambiguous = max(saw_ambiguous, count)
    if saw_ambiguous:
        return "AMBIGUOUS", saw_ambiguous
    return None, 0


def edit_file(path: str, old_string: str, new_string: str = "",
              replace_all: bool = False) -> str:
    """Surgically replace a snippet in an existing file (prefer this over a full
    overwrite). old_string should match the file; if it isn't byte-identical a
    bounded fuzzy cascade (whitespace/indentation tolerant) still locates it.
    The edit is REFUSED — never guessed — when no confident, unique match exists.
    Returns a small diff so the change is verifiable."""
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
        # newline="" so we see the TRUE on-disk line endings (no translation),
        # letting us restore them after editing.
        with open(full, encoding="utf-8", errors="replace", newline="") as f:
            raw = f.read()
    except Exception as e:
        return f"ERROR reading {path}: {e}"

    # Normalize line endings for matching; restore the file's original ending on write.
    ending = "\r\n" if "\r\n" in raw else "\n"
    before = raw.replace("\r\n", "\n")
    old_n = old_string.replace("\r\n", "\n")
    new_n = new_string.replace("\r\n", "\n")

    candidate, count = _find_match(before, old_n, replace_all)
    if candidate is None:
        return (f"ERROR: old_string not found in {path} (tried exact + whitespace/indentation "
                "tolerant matching). Read the file again and copy the exact current text to "
                "replace, including surrounding context.")
    if candidate == "AMBIGUOUS":
        return (f"ERROR: the snippet matches {count} places in {path}; it must be unique. "
                "Include more surrounding lines to target one spot, or set replace_all=true.")

    after = (before.replace(candidate, new_n) if replace_all
             else before.replace(candidate, new_n, 1))
    if after == before:
        return f"No change: new_string is identical to the matched text in {path}."
    try:
        with open(full, "w", encoding="utf-8", newline="") as f:
            f.write(after.replace("\n", ending) if ending == "\r\n" else after)
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


# ---- per-task sub-workspace heuristic (orchestration issue #6) -------------
# OFF by default — only consulted when the server enables AGENT_TASK_SUBWORKSPACE.
# A single chat session shares one workspace; when a user builds several unrelated
# things in one chat their files collide and confuse later turns. When enabled, a
# request that clearly STARTS A NEW standalone build gets its own subfolder.
_BUILD_RE = re.compile(
    r"\b(build|create|make|start|scaffold|generate)\b.*?\b(app|application|api|site|website|"
    r"web ?page|page|tool|script|project|service|cli|bot|game|dashboard|website)\b",
    re.IGNORECASE | re.DOTALL)
_FOLLOWUP_RE = re.compile(
    r"\b(the project|the app|earlier|previous|continue|keep going|add to|update the|"
    r"fix the|same|that we|it again|the existing|above)\b", re.IGNORECASE)
_SLUG_STOP = {"build", "create", "make", "start", "scaffold", "generate", "a", "an",
              "the", "me", "please", "with", "and", "for", "to", "new", "that"}


def fresh_build_slug(text: str):
    """Return a short folder slug if `text` reads like a request to START A NEW
    standalone build (and not a follow-up to existing work); else None. Pure +
    deterministic — the caller decides whether to actually use a sub-workspace."""
    t = text or ""
    if not _BUILD_RE.search(t) or _FOLLOWUP_RE.search(t):
        return None
    words = [w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in _SLUG_STOP]
    slug = "-".join(words[:4]) or "project"
    return ("proj_" + slug)[:48]


# ---- code search (grep / glob) ---------------------------------------------
# Design inspired by OpenCode's grep/glob tools (which shell to ripgrep); ours is
# pure-Python and confined to the workspace via _safe(), so it adds no dependency
# and can't read outside the sandbox. Lets an agent FIND code instead of listing +
# reading whole files (cheaper + far less context). See THIRD_PARTY.md.
_SEARCH_CAP = 100
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".skills", ".mypy_cache",
              "dist", "build", ".pytest_cache"}


def grep(pattern: str, include: str = None, path: str = ".") -> str:
    """Search file CONTENTS for a regex across the workspace. Returns up to 100
    `relpath:lineno: line` matches. `include` is an optional filename glob
    (e.g. '*.py'); `path` scopes the search to a subdirectory."""
    try:
        root = _safe(path)
    except ValueError as e:
        return f"ERROR: {e}"
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"ERROR: invalid regex: {e}"
    base = current_workspace()
    results, truncated = [], False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in sorted(filenames):
            if include and not fnmatch.fnmatch(fn, include):
                continue
            fpath = os.path.join(dirpath, fn)
            rel = os.path.relpath(fpath, base).replace(os.sep, "/")
            try:
                with open(fpath, encoding="utf-8", errors="ignore") as f:
                    for lineno, line in enumerate(f, 1):
                        if rx.search(line):
                            results.append(f"{rel}:{lineno}: {line.rstrip()[:300]}")
                            if len(results) >= _SEARCH_CAP:
                                truncated = True
                                break
            except (OSError, UnicodeDecodeError):
                continue
            if truncated:
                break
        if truncated:
            break
    if not results:
        return f"No matches for /{pattern}/" + (f" in {include}" if include else "")
    out = "\n".join(results)
    if truncated:
        out += f"\n... (capped at {_SEARCH_CAP} matches — narrow the pattern or path)"
    return out


def glob(pattern: str, path: str = ".") -> str:
    """Find files by glob pattern (e.g. '**/*.py', 'src/*.ts'), newest first.
    Returns up to 100 workspace-relative paths. `path` scopes to a subdirectory."""
    try:
        root = _safe(path)
    except ValueError as e:
        return f"ERROR: {e}"
    base = current_workspace()
    try:
        matches = [p for p in Path(root).glob(pattern)
                   if p.is_file() and not any(part in _SKIP_DIRS for part in p.parts)]
    except (ValueError, OSError) as e:
        return f"ERROR: invalid glob pattern: {e}"

    def _mtime(p):
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0
    matches.sort(key=_mtime, reverse=True)
    truncated = len(matches) > _SEARCH_CAP
    rels = [os.path.relpath(str(p), base).replace(os.sep, "/") for p in matches[:_SEARCH_CAP]]
    if not rels:
        return f"No files match {pattern}"
    out = "\n".join(rels)
    if truncated:
        out += f"\n... (capped at {_SEARCH_CAP} — narrow the pattern)"
    return out


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
    "grep": grep,
    "glob": glob,
    "run_bash": run_bash,
}

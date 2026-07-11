"""
toolbelt.py — the TOOL REGISTRY (the third registry, beside models and agents).

A Tool bundles an OpenAI-format schema, the callable, a RISK label
(safe / write / critical) and a `requires_human` flag. Agents are granted a subset
of tools by name (least privilege, see config/agents.yaml).

Direction of dependencies (keeps core offline by default):
  - core registers only the built-in, sandboxed, OFFLINE file/shell tools below.
  - network capabilities (web, image, MCP) live in the top-level `tools/` package
    and register THEMSELVES here when that package is imported. core never imports
    `tools/`, so importing core alone pulls in no web/provider code.
"""
from dataclasses import dataclass
from typing import Callable, Optional

RISK_SAFE = "safe"          # read-only / no side effects
RISK_WRITE = "write"        # creates/changes files in the sandbox
RISK_CRITICAL = "critical"  # irreversible / destructive / runs arbitrary code


@dataclass
class Tool:
    name: str
    schema: dict             # OpenAI function-tool schema
    func: Callable
    risk: str = RISK_SAFE
    requires_human: bool = False
    description: str = ""


_REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    _REGISTRY[tool.name] = tool
    return tool


def register_fn(name, func, parameters, description="",
                risk=RISK_SAFE, requires_human=False) -> Tool:
    schema = {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    }
    return register(Tool(name, schema, func, risk, requires_human, description))


# Common names weak/open models emit for our tools (wrong word, not just wrong case).
# Maps an alias -> the real tool name; applied only after exact + case-insensitive miss.
_TOOL_ALIASES = {
    "bash": "run_bash", "shell": "run_bash", "sh": "run_bash", "exec": "run_bash",
    "search": "grep", "search_files": "grep", "find_in_files": "grep",
    "find": "glob", "find_files": "glob", "ls": "list_files", "cat": "read_file",
}


def get(name: str) -> Optional[Tool]:
    """Resolve a tool by name, tolerant of how weak models address tools: exact match
    first, then trimmed/case-insensitive (so `Write`/`Read ` resolve), then a small alias
    map (`bash`->`run_bash`, `search`->`grep`, ...). A wrong-case tool name was otherwise
    an `unknown tool` hard-fail — the single biggest cheap-model failure (OpenCode #234)."""
    if not name:
        return None
    t = _REGISTRY.get(name)
    if t:
        return t
    key = name.strip()
    t = _REGISTRY.get(key)
    if t:
        return t
    low = key.lower()
    for n, tool in _REGISTRY.items():          # case-insensitive match
        if n.lower() == low:
            return tool
    alias = _TOOL_ALIASES.get(low)
    return _REGISTRY.get(alias) if alias else None


def signature(tool: "Tool") -> str:
    """Readable param signature, e.g. 'write_file(path: string*, content: string*)'
    (* = required). Fed back when a model calls a tool with wrong/missing args so it can
    self-correct in one shot instead of looping (OpenCode-style repair feedback)."""
    fn = (tool.schema or {}).get("function", {}) or {}
    params = fn.get("parameters", {}) or {}
    props = params.get("properties", {}) or {}
    required = set(params.get("required", []) or [])
    parts = [f"{k}: {(spec or {}).get('type', 'any')}{'*' if k in required else ''}"
             for k, spec in props.items()]
    return f"{fn.get('name', '?')}({', '.join(parts)})"


def all_tools() -> dict[str, Tool]:
    return dict(_REGISTRY)


def names() -> list:
    return list(_REGISTRY)


def validate_args(tool: "Tool", args) -> Optional[str]:
    """Return None if `args` satisfy the tool's JSON schema, else a short error.

    Lenient on scalar type drift (a model sending a number as "4" is fine) but
    STRICT on the two failure modes that actually break a tool call: a missing
    required argument, and a structurally-wrong container (object/array/string
    confusion). On failure the agent loop feeds the error back so the model
    re-issues the call — instead of executing with broken args. Design inspired
    by OpenCode's pre-execution arg validation (see THIRD_PARTY.md)."""
    if not isinstance(args, dict):
        return "arguments must be a JSON object"
    params = (tool.schema.get("function", {}) or {}).get("parameters", {}) or {}
    props = params.get("properties", {}) or {}
    required = params.get("required", []) or []
    missing = [k for k in required if k not in args or args[k] is None]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}"
    for k, v in args.items():
        spec = props.get(k)
        if not spec:
            continue
        t = spec.get("type")
        if t == "string" and isinstance(v, (dict, list)):
            return f"argument '{k}' should be a string, got {type(v).__name__}"
        if t == "array" and not isinstance(v, list):
            return f"argument '{k}' should be an array"
        if t == "object" and not isinstance(v, dict):
            return f"argument '{k}' should be an object"
    # Unknown keys = the model used a WRONG name (e.g. fileContent for content). Reject so
    # it doesn't reach the tool (which would TypeError on an unexpected kwarg) and the model
    # gets told the real param names via the signature in the loop's feedback.
    unknown = [k for k in args if props and k not in props]
    if unknown:
        return f"unknown argument(s): {', '.join(unknown)}"
    return None


def schemas_for(tool_names) -> list:
    """OpenAI tool schemas for the given names (silently skips unknown names)."""
    out = []
    for n in tool_names:
        t = _REGISTRY.get(n)
        if t:
            out.append(t.schema)
    return out


def _obj(props, required=None):
    return {"type": "object", "properties": props, "required": required or []}


# ---- built-in OFFLINE sandboxed tools (file/shell) --------------------------
from .tools import (read_file, write_file, edit_file, list_files, run_bash,  # noqa: E402
                    parse_document, grep, glob, apply_patch)

register_fn(
    "read_file", lambda path, offset=1, limit=None: read_file(path, offset, limit),
    _obj({"path": {"type": "string"},
          "offset": {"type": "integer", "description": "1-indexed first line to read (default 1)"},
          "limit": {"type": "integer", "description": "max lines to return (default/cap 2000)"}},
         ["path"]),
    "Read a file in the workspace as numbered lines. Large files are capped (~2000 lines / "
    "50KB); use offset/limit to page through the rest (the footer tells you the next offset).",
    RISK_SAFE,
)
register_fn(
    "parse_document", lambda path: parse_document(path),
    _obj({"path": {"type": "string"}}, ["path"]),
    "Convert a document (PDF/DOCX/PPTX/XLSX/HTML) in the workspace to clean markdown — "
    "use this to read a spec/FRS/report with its structure (headings, tables) intact.", RISK_SAFE,
)
register_fn(
    "list_files", lambda directory=".": list_files(directory),
    _obj({"directory": {"type": "string"}}),
    "List files in a workspace directory (default: root).", RISK_SAFE,
)
register_fn(
    "grep", lambda pattern, include=None, path=".": grep(pattern, include, path),
    _obj({"pattern": {"type": "string", "description": "regex to search file contents for"},
          "include": {"type": "string", "description": "optional filename glob, e.g. '*.py'"},
          "path": {"type": "string", "description": "subdirectory to search (default: root)"}},
         ["pattern"]),
    "Search file CONTENTS across the workspace for a regex (returns relpath:line: match, "
    "capped at 100). Use this to FIND code instead of reading whole files.", RISK_SAFE,
)
register_fn(
    "glob", lambda pattern, path=".": glob(pattern, path),
    _obj({"pattern": {"type": "string", "description": "glob, e.g. '**/*.py' or 'src/*.ts'"},
          "path": {"type": "string", "description": "subdirectory to search (default: root)"}},
         ["pattern"]),
    "Find files by name/glob pattern across the workspace (newest first, capped at 100).",
    RISK_SAFE,
)
register_fn(
    "write_file", lambda path, content: write_file(path, content),
    _obj({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    "Create a NEW file (or fully overwrite one) in the workspace. For changing part "
    "of an existing file, prefer edit_file.", RISK_WRITE,
)
register_fn(
    "edit_file",
    lambda path, old_string, new_string="", replace_all=False: edit_file(path, old_string, new_string, replace_all),
    _obj({"path": {"type": "string"},
          "old_string": {"type": "string", "description": "exact text to replace (incl. whitespace); must be unique unless replace_all"},
          "new_string": {"type": "string", "description": "replacement text (\"\" to delete the snippet)"},
          "replace_all": {"type": "boolean", "description": "replace every occurrence (default false)"}},
         ["path", "old_string", "new_string"]),
    "Make a precise edit to an EXISTING file by replacing an exact snippet. Prefer this "
    "over write_file for changes so you don't rewrite (and risk breaking) the whole file. "
    "Read the file first to copy the exact old_string.", RISK_WRITE,
)
register_fn(
    "apply_patch", lambda patch: apply_patch(patch),
    _obj({"patch": {"type": "string",
                    "description": "a unified diff (git-style `diff -u`): '--- a/path', "
                                   "'+++ b/path', '@@' hunks with ' '/'-'/'+' lines. Can touch "
                                   "multiple files."}}, ["patch"]),
    "Apply a multi-file unified diff in ONE call — the efficient way to make a change that "
    "spans several files or several spots. Each hunk is located tolerantly (like edit_file); "
    "an unmatchable hunk is refused and reported. Use write_file for a brand-new file.",
    RISK_WRITE,
)
import os as _os
_docker_configured = bool(_os.environ.get("AGENT_BASH_DOCKER_IMAGE", "").strip())
if _docker_configured:
    # Docker sandbox configured: sandboxed (RISK_WRITE), auto-approved in auto/trusted mode.
    register_fn(
        "run_bash", lambda command: run_bash(command),
        _obj({"command": {"type": "string"}}, ["command"]),
        "Run a shell command in the sandboxed Docker workspace (tests, builds, executing code).",
        RISK_WRITE,
        requires_human=False,
    )
else:
    # Docker NOT configured: register run_bash as CRITICAL + requires_human so every call
    # goes through human approval rather than auto-executing. The function returns an
    # informative error; the human gate prevents silent spin-loops. Once
    # AGENT_BASH_DOCKER_IMAGE is set and the server restarts, the tool upgrades to RISK_WRITE.
    # Always registered (never None) so the policy gate and toolbelt tests work correctly.
    register_fn(
        "run_bash", lambda command: run_bash(command),
        _obj({"command": {"type": "string"}}, ["command"]),
        "Run a shell command (requires Docker sandbox — set AGENT_BASH_DOCKER_IMAGE to enable).",
        RISK_CRITICAL,
        requires_human=True,
    )

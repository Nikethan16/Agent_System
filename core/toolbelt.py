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


def get(name: str) -> Optional[Tool]:
    return _REGISTRY.get(name)


def all_tools() -> dict[str, Tool]:
    return dict(_REGISTRY)


def names() -> list:
    return list(_REGISTRY)


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
                    parse_document, grep, glob)

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

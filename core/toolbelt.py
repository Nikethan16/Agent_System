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
from .tools import read_file, write_file, edit_file, list_files, run_bash, parse_document  # noqa: E402

register_fn(
    "read_file", lambda path: read_file(path),
    _obj({"path": {"type": "string"}}, ["path"]),
    "Read the full contents of a file in the workspace.", RISK_SAFE,
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
    # Docker sandbox is configured: run_bash is sandboxed (RISK_WRITE, no human gate).
    # Agents can use it freely in auto/trusted mode; the Docker container provides containment.
    register_fn(
        "run_bash", lambda command: run_bash(command),
        _obj({"command": {"type": "string"}}, ["command"]),
        "Run a shell command in the sandboxed Docker workspace (tests, builds, executing code).",
        RISK_WRITE,
        requires_human=False,
    )
# When Docker is NOT configured, run_bash is not registered at all. Agents won't see
# it as an available tool, so they verify by code inspection and finish cleanly instead
# of spinning on a tool that can only return an error. run_bash auto-enables once
# AGENT_BASH_DOCKER_IMAGE is set (restart the server).

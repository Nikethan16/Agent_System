"""
lint.py — real diagnostics (LSP-grade) fed into the agent loop.

Upgrades the syntax/pyflakes stand-in: when a real static analyser is on PATH we use
it, otherwise we fall back to the in-process pyflakes + compile() check so behaviour
never regresses on a machine without the tool.

  * Python  →  `ruff` if available (undefined names, bad imports, many bug patterns,
               style), else pyflakes (in-process) + compile() for syntax.
  * JSON / YAML / TOML  →  in-process parse (syntax only).

Everything here is STATIC analysis — it never executes the file under inspection —
and is confined to the session workspace (invariant #5): the analyser runs with the
workspace as its cwd, only workspace paths are passed to it, output is capped, and a
wall-clock timeout bounds it. No network, no provider SDK (invariant #4).
"""
import os
import json
import shutil
import subprocess

from . import tools

_TIMEOUT = int(os.environ.get("AGENT_LSP_TIMEOUT", "20"))
_MAX_DIAGS = 40           # never flood the agent's context with a wall of lint
_PY_EXT = ".py"


def _ruff_exe():
    """Path to a `ruff` executable, or None. Cached per process."""
    if not hasattr(_ruff_exe, "_cached"):
        _ruff_exe._cached = (
            os.environ.get("AGENT_RUFF_PATH", "").strip() or shutil.which("ruff") or None
        )
    return _ruff_exe._cached


def available() -> bool:
    """True when a real language analyser (beyond the in-process fallback) is present."""
    return bool(_ruff_exe())


def _run_ruff(args, cwd, stdin_text=None):
    exe = _ruff_exe()
    if not exe:
        return None
    argv = [exe, "check", "--output-format", "json", "--force-exclude", *args]
    try:
        r = subprocess.run(argv, cwd=cwd, input=stdin_text, capture_output=True,
                           text=True, timeout=_TIMEOUT)
    except Exception:
        return None
    out = (r.stdout or "").strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except Exception:
        return None
    diags = []
    for d in data:
        loc = d.get("location") or {}
        diags.append({
            "line": loc.get("row"), "col": loc.get("column"),
            "code": d.get("code") or "", "message": d.get("message") or "",
            "severity": d.get("severity") or "error",
            "file": d.get("filename") or "",
            "fix": (d.get("fix") or {}).get("message") if d.get("fix") else None,
        })
    return diags


def _pyflakes(path, content):
    """In-process fallback: compile() for syntax, then pyflakes for deeper issues."""
    diags = []
    try:
        compile(content, os.path.basename(path), "exec")
    except SyntaxError as e:
        return [{"line": e.lineno, "col": e.offset, "code": "E999",
                 "message": f"SyntaxError: {e.msg}", "severity": "error", "file": path, "fix": None}]
    try:
        from pyflakes.api import check as _check
        from pyflakes.reporter import Reporter
    except ImportError:
        return diags
    import io
    out = io.StringIO()
    try:
        from pyflakes.api import check  # noqa: F401
        n = _check(content, os.path.basename(path), Reporter(out, io.StringIO()))
    except Exception:
        return diags
    if not n:
        return diags
    for ln in out.getvalue().splitlines():
        # pyflakes lines look like "name:line:col message"
        parts = ln.split(":", 3)
        if len(parts) >= 4:
            try:
                diags.append({"line": int(parts[1]), "col": int(parts[2]),
                              "code": "", "message": parts[3].strip(),
                              "severity": "warning", "file": path, "fix": None})
                continue
            except ValueError:
                pass
        if ln.strip():
            diags.append({"line": None, "col": None, "code": "", "message": ln.strip(),
                          "severity": "warning", "file": path, "fix": None})
    return diags


def diagnose(path: str, content: str = None) -> list:
    """Diagnostics for one file. `content` (unsaved buffer) is analysed via the tool's
    stdin when given, else the on-disk file is read. Path is workspace-confined."""
    full = tools._safe(path)
    ws = tools.current_workspace()
    ext = os.path.splitext(path)[1].lower()

    if ext == _PY_EXT:
        if _ruff_exe():
            if content is not None:
                diags = _run_ruff(["--stdin-filename", full, "-"], ws, stdin_text=content)
            else:
                diags = _run_ruff([full], ws)
            if diags is not None:
                return diags[:_MAX_DIAGS]
        # no ruff (or it failed) → in-process fallback
        if content is None:
            try:
                with open(full, encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                return []
        return _pyflakes(path, content)[:_MAX_DIAGS]

    # Non-Python: cheap in-process syntax parse.
    if content is None:
        try:
            with open(full, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            return []
    try:
        if ext == ".json" and content.strip():
            json.loads(content)
        elif ext in (".yaml", ".yml"):
            import yaml
            yaml.safe_load(content)
        elif ext == ".toml":
            import tomllib
            tomllib.loads(content)
    except Exception as e:
        return [{"line": getattr(e, "lineno", None), "col": None, "code": "",
                 "message": f"{type(e).__name__}: {str(e)[:160]}", "severity": "error",
                 "file": path, "fix": None}]
    return []


def _rel(full: str, ws: str) -> str:
    try:
        return os.path.relpath(full, ws).replace("\\", "/")
    except ValueError:
        return full


def diagnose_path(path: str = ".") -> list:
    """Diagnostics for a file OR a directory (Python files within it), workspace-confined."""
    full = tools._safe(path)
    ws = tools.current_workspace()
    if os.path.isdir(full):
        if _ruff_exe():
            diags = _run_ruff([full], ws)
            if diags is not None:
                return diags[:_MAX_DIAGS]
        # fallback: walk .py files (bounded) and pyflakes each
        out, seen = [], 0
        for root, dirs, files in os.walk(full):
            dirs[:] = [d for d in dirs if d not in tools._SKIP_DIRS]
            for fn in files:
                if fn.endswith(_PY_EXT):
                    out.extend(diagnose(_rel(os.path.join(root, fn), ws)))
                    seen += 1
                    if seen >= 60 or len(out) >= _MAX_DIAGS:
                        return out[:_MAX_DIAGS]
        return out[:_MAX_DIAGS]
    return diagnose(path)


def format_diagnostics(path: str, diags: list, ws: str = None) -> str:
    """A compact, agent-readable rendering, grouped by file, capped."""
    if not diags:
        return f"No diagnostics for {path} — clean."
    ws = ws or tools.current_workspace()
    lines = [f"{len(diags)} diagnostic(s):"]
    for d in diags[:_MAX_DIAGS]:
        loc = f":{d['line']}" if d.get("line") else ""
        loc += f":{d['col']}" if d.get("col") else ""
        code = f" {d['code']}" if d.get("code") else ""
        where = _rel(d["file"], ws) if d.get("file") else path
        fix = f"  [fix: {d['fix']}]" if d.get("fix") else ""
        lines.append(f"  {where}{loc}{code}: {d['message']}{fix}")
    return "\n".join(lines)


def postedit_python(path: str, content: str) -> str:
    """Post-edit warning string for a just-written .py file (empty when clean).
    Called from tools.write_file/edit_file. Uses the real analyser when present."""
    diags = diagnose(path, content)
    errs = [d for d in diags if d.get("severity") == "error"]
    shown = (errs or diags)[:5]
    if not shown:
        return ""
    engine = "ruff" if _ruff_exe() else "pyflakes"
    parts = []
    for d in shown:
        loc = f"line {d['line']}" if d.get("line") else ""
        code = f" {d['code']}" if d.get("code") else ""
        parts.append(f"{loc}{code}: {d['message']}".strip())
    kind = "SYNTAX/DIAGNOSTICS" if errs else "DIAGNOSTICS"
    return (f"\n\n⚠️ {kind} ({engine}): " + " | ".join(parts) +
            ". Likely bugs — fix them before continuing.")

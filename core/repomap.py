"""repomap.py — a COMPACT map of a codebase: the file tree + the key symbols (functions /
classes) in each source file, so an agent can understand a repo's structure WITHOUT reading
every file. This is what lets the architect / coder scale past small repos — they read the
map first, then open only the specific files they actually need.

Bounded by design (file count + total chars) so it stays cheap even on a large repo. Pure
stdlib, offline, read-only. Python symbols come from the AST; other languages from a light
regex; everything else is just listed.
"""
from __future__ import annotations

import ast
import os
import re

_SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__", "node_modules", ".mypy_cache",
              ".pytest_cache", ".ruff_cache", "dist", "build", ".next", ".nuxt", ".idea",
              ".vscode", "site-packages", ".skills", ".cache", "coverage", ".tox", "target",
              "vendor", ".gradle", "bin", "obj"}
_CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rb", ".rs", ".java", ".kt",
             ".c", ".h", ".cc", ".cpp", ".cs", ".php", ".swift", ".scala", ".m", ".mm"}
_NOTE_FILES = {"readme", "readme.md", "makefile", "dockerfile", "requirements.txt",
               "pyproject.toml", "package.json", "go.mod", "cargo.toml", "setup.py",
               "setup.cfg", "tsconfig.json", "pom.xml", "build.gradle", ".env.example"}

_JS_SYM = re.compile(
    r"(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)"
    r"|(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(")


def _py_symbols(src: str) -> list[str]:
    """Top-level functions + classes (with their public methods) via the AST."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(node.name + "()")
        elif isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and not n.name.startswith("_")][:8]
            out.append(f"{node.name}[{', '.join(methods)}]" if methods else node.name)
    return out


def _js_symbols(src: str) -> list[str]:
    seen: list[str] = []
    for m in _JS_SYM.finditer(src):
        name = m.group(1) or m.group(2)
        if name and name not in seen:
            seen.append(name)
        if len(seen) >= 20:
            break
    return [s + "()" for s in seen]


def _symbols(path: str) -> list[str]:
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            src = f.read(200_000)          # cap per-file read
    except OSError:
        return []
    if ext == ".py":
        return _py_symbols(src)
    if ext in (".js", ".jsx", ".ts", ".tsx"):
        return _js_symbols(src)
    return []


def build_map(base: str, max_files: int = 300, max_chars: int = 6000) -> str:
    """Return a compact map of the tree under `base` (an absolute directory path)."""
    if not base or not os.path.isdir(base):
        return ""
    by_dir: dict[str, list[str]] = {}
    n_files = 0
    truncated = False
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS and not d.startswith("."))
        rel_dir = os.path.relpath(root, base).replace("\\", "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        for fn in sorted(files):
            if fn.startswith("."):
                continue
            ext = os.path.splitext(fn)[1].lower()
            is_code = ext in _CODE_EXT
            is_note = fn.lower() in _NOTE_FILES
            if not (is_code or is_note):
                continue
            if n_files >= max_files:
                truncated = True
                break
            n_files += 1
            syms = _symbols(os.path.join(root, fn)) if is_code else []
            label = fn if not syms else f"{fn}  {', '.join(syms[:12])}"
            by_dir.setdefault(rel_dir, []).append(label)
        if truncated:
            break

    if not by_dir:
        return f"CODEBASE MAP: (no source files found under {os.path.basename(base) or base})"

    name = os.path.basename(os.path.normpath(base)) or base
    lines = [f"CODEBASE MAP ({name}, {n_files} source file(s)"
             + (", truncated" if truncated else "") + "):"]
    for d in sorted(by_dir):
        lines.append(f"{d}/" if d else "(root)")
        for entry in by_dir[d]:
            lines.append(f"  {entry}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n  … (map truncated — use grep/glob/read_file for detail)"
    return text

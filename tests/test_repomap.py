"""The repo map gives an agent a compact tree + key symbols so it can grok a codebase
without reading every file (the thing that lets the pipeline scale past small repos)."""
import os

from core import repomap


def _write(root, rel, content):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def test_python_symbols_and_tree(tmp_path):
    root = str(tmp_path)
    _write(root, "pkg/core.py",
           "def add(a, b):\n    return a + b\n\n\nclass Store:\n    def load(self): ...\n"
           "    def save(self): ...\n    def _private(self): ...\n")
    _write(root, "pkg/__init__.py", "")
    _write(root, "README.md", "# hi\n")
    m = repomap.build_map(root)
    assert "CODEBASE MAP" in m
    assert "pkg/" in m and "core.py" in m
    assert "add()" in m                       # top-level function
    assert "Store[load, save]" in m           # class with PUBLIC methods only
    assert "_private" not in m                 # private methods are hidden
    assert "README.md" in m                    # note files are listed


def test_skips_junk_dirs_and_is_bounded(tmp_path):
    root = str(tmp_path)
    _write(root, "app.py", "def main(): ...\n")
    _write(root, "node_modules/dep/index.js", "export function x(){}\n")
    _write(root, ".venv/lib/thing.py", "def hidden(): ...\n")
    _write(root, "__pycache__/app.cpython-311.pyc", "junk")
    m = repomap.build_map(root)
    assert "app.py" in m and "main()" in m
    assert "node_modules" not in m and "hidden()" not in m   # skip dirs excluded


def test_js_symbols(tmp_path):
    root = str(tmp_path)
    _write(root, "src/util.ts",
           "export function parse(x){}\nexport const build = () => {}\nclass Widget {}\n")
    m = repomap.build_map(root)
    assert "util.ts" in m
    assert "parse()" in m and "Widget()" in m


def test_empty_and_bad_dir():
    assert repomap.build_map("/does/not/exist/xyz") == ""

"""Junk-dir hygiene: list_files / glob must not surface .git, node_modules, etc. so agents
don't waste reads exploring them."""
import os
import tempfile

from core import tools


def _seed():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, ".git"))
    open(os.path.join(d, ".git", "HEAD"), "w").close()
    os.makedirs(os.path.join(d, "node_modules", "pkg"))
    open(os.path.join(d, "node_modules", "pkg", "index.js"), "w").close()
    open(os.path.join(d, "README.md"), "w").close()
    return d


def test_list_files_hides_junk():
    with tools.using_workspace(_seed()):
        out = tools.list_files(".")
        assert "README.md" in out
        assert ".git" not in out and "node_modules" not in out


def test_glob_skips_junk():
    with tools.using_workspace(_seed()):
        out = tools.glob("**/*")
        assert "README.md" in out
        assert ".git" not in out and "node_modules" not in out

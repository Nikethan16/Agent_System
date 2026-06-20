"""Tests for the /ws mount-prefix mapping in _safe (orch #7)."""
import os
import tempfile

import pytest

from core import tools
from core.tools import using_workspace


@pytest.fixture()
def ws():
    with tempfile.TemporaryDirectory() as d:
        with using_workspace(d):
            yield d


def test_container_path_maps_to_workspace(ws):
    # A /ws/... path (as seen inside the Docker sandbox) resolves under the workspace.
    full = tools._safe("/ws/foo/bar.py")
    assert os.path.normpath(full) == os.path.normpath(os.path.join(ws, "foo", "bar.py"))


def test_bare_container_root_maps_to_workspace(ws):
    full = tools._safe("/ws")
    assert os.path.normpath(full) == os.path.normpath(ws)


def test_write_then_edit_via_container_path(ws):
    # End-to-end: write at /ws/app.py then edit it via the same container path.
    assert "Wrote" in tools.write_file("/ws/app.py", "x = 1\n")
    out = tools.edit_file("/ws/app.py", "x = 1", "x = 2")
    assert "Edited" in out
    with open(os.path.join(ws, "app.py")) as f:
        assert f.read() == "x = 2\n"


def test_real_escape_still_blocked(ws):
    # The mapping must NOT weaken containment: a genuine escape still raises.
    with pytest.raises(ValueError):
        tools._safe("../../../etc/passwd")


def test_ws_lookalike_not_overmapped(ws):
    # '/wsX' is NOT the mount prefix; it should resolve relative (and be blocked
    # as an absolute escape), not be treated as '/ws'.
    with pytest.raises(ValueError):
        tools._safe("/wsother/secret")

"""Tests for user-authored /commands (core/commands.py)."""
import os

import pytest

from core import commands, tools


@pytest.fixture
def cmd_dir(tmp_path, monkeypatch):
    """An isolated command dir wired in via AGENT_COMMANDS_DIR, plus a scratch
    workspace so @file / !shell resolve somewhere safe."""
    d = tmp_path / "cmds"
    d.mkdir()
    monkeypatch.setenv("AGENT_COMMANDS_DIR", str(d))
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(tools, "WORKSPACE", str(ws), raising=False)
    return d, ws


def _write(d, name, body):
    (d / f"{name}.md").write_text(body, encoding="utf-8")


def test_load_and_list_parses_frontmatter(cmd_dir):
    d, _ = cmd_dir
    _write(d, "review", "---\ndescription: Review a file\nargument-hint: \"[path]\"\n---\nReview $ARGUMENTS")
    cmds = commands.load_commands()
    assert "review" in cmds
    assert cmds["review"]["description"] == "Review a file"
    assert cmds["review"]["argument_hint"] == "[path]"
    assert cmds["review"]["body"] == "Review $ARGUMENTS"

    listing = commands.list_commands()
    assert {"name": "review", "description": "Review a file", "argument_hint": "[path]"} in listing


def test_is_command_only_matches_known(cmd_dir):
    d, _ = cmd_dir
    _write(d, "greet", "Hello $ARGUMENTS")
    assert commands.is_command("/greet world") is True
    assert commands.is_command("/greet") is True
    assert commands.is_command("/unknown x") is False   # not a real command
    assert commands.is_command("just a message") is False
    assert commands.is_command("/path/to/thing") is False  # bare slash, no such command


def test_expand_arguments_and_positional(cmd_dir):
    d, ws = cmd_dir
    _write(d, "greet", "Hi $1 and $2 — all: $ARGUMENTS")
    out = commands.expand("/greet alice bob", str(ws))
    assert out == "Hi alice and bob — all: alice bob"


def test_expand_missing_positional_is_empty(cmd_dir):
    d, ws = cmd_dir
    _write(d, "g", "[$1][$2][$3]")
    assert commands.expand("/g only", str(ws)) == "[only][][]"


def test_expand_file_inlines_workspace_content(cmd_dir):
    d, ws = cmd_dir
    (ws / "hello.txt").write_text("line one\nline two\n", encoding="utf-8")
    _write(d, "show", "Here:\n@$1")
    out = commands.expand("/show hello.txt", str(ws))
    assert "line one" in out
    assert "=== hello.txt ===" in out


def test_expand_file_missing_is_graceful(cmd_dir):
    d, ws = cmd_dir
    _write(d, "show", "@nope.txt")
    out = commands.expand("/show", str(ws))
    assert "could not read" in out.lower() or "nope.txt" in out


def test_expand_shell_uses_sandbox_no_host_exec(cmd_dir, monkeypatch):
    """!`shell` must go through run_bash. With no Docker image configured, run_bash
    refuses rather than running on the host — the output should say so, not execute."""
    d, ws = cmd_dir
    monkeypatch.delenv("AGENT_BASH_DOCKER_IMAGE", raising=False)
    monkeypatch.delenv("AGENT_DISABLE_BASH", raising=False)
    _write(d, "run", "out: !`echo hi`")
    out = commands.expand("/run", str(ws))
    assert "$ echo hi" in out
    assert "AGENT_BASH_DOCKER_IMAGE" in out   # the run_bash "no sandbox" notice


def test_expand_shell_routes_command_to_run_bash(cmd_dir, monkeypatch):
    """The exact command (with args substituted) reaches run_bash."""
    d, ws = cmd_dir
    seen = {}
    monkeypatch.setattr(tools, "run_bash", lambda c: (seen.__setitem__("cmd", c), "OK")[1])
    _write(d, "ls", "!`ls $1`")
    out = commands.expand("/ls subdir", str(ws))
    assert seen["cmd"] == "ls subdir"
    assert "OK" in out


def test_argument_cannot_smuggle_new_tokens(cmd_dir, monkeypatch):
    """A shell/file token in USER ARGS must be treated as literal text, never executed."""
    d, ws = cmd_dir
    calls = []
    monkeypatch.setattr(tools, "run_bash", lambda c: calls.append(c) or "ran")
    _write(d, "echo", "$ARGUMENTS")
    out = commands.expand("/echo !`whoami` @secret.txt", str(ws))
    assert calls == []                      # no shell ran
    assert out == "!`whoami` @secret.txt"   # left verbatim


def test_non_command_passes_through(cmd_dir):
    _, ws = cmd_dir
    assert commands.expand("just a normal message", str(ws)) == "just a normal message"


def test_user_dir_overrides_builtin(cmd_dir):
    """A command in AGENT_COMMANDS_DIR shadows a shipped one of the same name."""
    d, ws = cmd_dir
    _write(d, "review", "custom body $ARGUMENTS")
    out = commands.expand("/review x", str(ws))
    assert out == "custom body x"

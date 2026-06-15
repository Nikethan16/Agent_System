"""
Unit tests for tools/github.py — git operations + GitHub REST.

All subprocess calls are mocked so these run fully offline with no git binary,
no network, and no GITHUB_TOKEN required. The integration script
scripts/test_repo_mode.py covers the live end-to-end flow.
"""
import os
import types
from unittest.mock import patch, MagicMock, call

import pytest

# Import github directly (avoids tools/__init__.py which imports image.py → litellm,
# which crashes in this container due to a broken cryptography/cffi install).
import importlib, sys
_spec = importlib.util.spec_from_file_location(
    "tools.github",
    __import__("pathlib").Path(__file__).parent.parent / "tools" / "github.py"
)
gh = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("tools.github", gh)
_spec.loader.exec_module(gh)


# ---- fixtures ---------------------------------------------------------------

@pytest.fixture(autouse=True)
def fake_workspace(tmp_path, monkeypatch):
    """Every test gets a fresh tmp workspace.
    Patches current_workspace() on the github module AND on core.tools so
    _safe() resolves paths relative to the same tmp dir."""
    monkeypatch.setattr(gh, "current_workspace", lambda: str(tmp_path))
    import core.tools as ct
    monkeypatch.setattr(ct, "current_workspace", lambda: str(tmp_path))
    monkeypatch.setattr(ct, "WORKSPACE", str(tmp_path))
    yield str(tmp_path)


def _make_proc(rc=0, stdout="", stderr=""):
    """Build a fake subprocess.CompletedProcess."""
    p = MagicMock()
    p.returncode = rc
    p.stdout = stdout
    p.stderr = stderr
    return p


# ---- _fmt -------------------------------------------------------------------

class TestFmt:
    def test_exit_only_when_no_output(self):
        out = gh._fmt(0, "", "")
        assert out == "exit=0"

    def test_stdout_wrapped_as_untrusted(self):
        out = gh._fmt(0, "some output", "")
        assert "<untrusted_git_output>" in out
        assert "some output" in out
        assert "exit=0" in out

    def test_stderr_wrapped_as_untrusted(self):
        out = gh._fmt(1, "", "fatal: not a git repo")
        assert "<untrusted_git_stderr>" in out
        assert "fatal: not a git repo" in out

    def test_both_wrapped_separately(self):
        out = gh._fmt(0, "stdout text", "stderr text")
        assert "<untrusted_git_output>" in out
        assert "<untrusted_git_stderr>" in out


# ---- git_clone --------------------------------------------------------------

class TestGitClone:
    def test_rejects_invalid_url(self):
        result = gh.git_clone("ftp://bad.com/repo")
        assert result.startswith("ERROR")

    def test_rejects_empty_url(self):
        result = gh.git_clone("")
        assert result.startswith("ERROR")

    def test_clones_https_url(self, fake_workspace):
        with patch("subprocess.run", return_value=_make_proc(0, "", "Cloning into 'repo'...")) as mock_run:
            result = gh.git_clone("https://github.com/example/repo.git")
        assert "exit=0" in result
        cmd = mock_run.call_args[0][0]
        assert "clone" in cmd

    def test_token_injected_into_clone_url(self, fake_workspace, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        captured = []
        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return _make_proc(0, "", "")
        with patch("subprocess.run", side_effect=fake_run):
            gh.git_clone("https://github.com/example/repo.git")
        clone_cmd = captured[0]
        clone_url = next(a for a in clone_cmd if "github.com" in a)
        assert "oauth2:ghp_test123@" in clone_url

    def test_token_not_in_output(self, fake_workspace, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
        with patch("subprocess.run", return_value=_make_proc(0, "https://oauth2:ghp_secret@github.com/r", "")):
            result = gh.git_clone("https://github.com/example/repo.git")
        assert "ghp_secret" not in result

    def test_directory_arg_sanitized(self, fake_workspace):
        with patch("subprocess.run", return_value=_make_proc(0, "", "")) as mock_run:
            gh.git_clone("https://github.com/example/repo.git", "../../../etc/evil")
        cmd = mock_run.call_args[0][0]
        # The directory arg must not contain path-traversal characters
        dir_arg = cmd[-1]
        assert ".." not in dir_arg
        assert "/" not in dir_arg

    def test_optional_directory_passed(self, fake_workspace):
        with patch("subprocess.run", return_value=_make_proc(0, "", "")) as mock_run:
            gh.git_clone("https://github.com/example/repo.git", "myrepo")
        cmd = mock_run.call_args[0][0]
        assert "myrepo" in cmd


# ---- git_status / git_diff / git_log ----------------------------------------

class TestReadOnlyOps:
    def test_git_status_calls_status(self, fake_workspace):
        with patch("subprocess.run", return_value=_make_proc(0, "nothing to commit", "")) as m:
            result = gh.git_status()
        assert "git" in m.call_args[0][0]
        assert "status" in m.call_args[0][0]
        assert "<untrusted_git_output>" in result

    def test_git_diff_no_path(self, fake_workspace):
        with patch("subprocess.run", return_value=_make_proc(0, "+line added", "")) as m:
            result = gh.git_diff()
        cmd = m.call_args[0][0]
        assert "diff" in cmd
        assert "<untrusted_git_output>" in result

    def test_git_log_clamps_n(self, fake_workspace):
        with patch("subprocess.run", return_value=_make_proc(0, "abc123 msg", "")) as m:
            gh.git_log(n=999)
        cmd = m.call_args[0][0]
        # n is clamped to 50
        assert "-50" in cmd

    def test_git_log_minimum_one(self, fake_workspace):
        with patch("subprocess.run", return_value=_make_proc(0, "", "")) as m:
            gh.git_log(n=0)
        cmd = m.call_args[0][0]
        assert "-1" in cmd


# ---- git_checkout_branch ----------------------------------------------------

class TestCheckoutBranch:
    def test_rejects_invalid_branch_name(self):
        result = gh.git_checkout_branch("branch with spaces")
        assert result.startswith("ERROR")

    def test_rejects_empty_branch(self):
        result = gh.git_checkout_branch("")
        assert result.startswith("ERROR")

    def test_rejects_shell_injection_chars(self):
        result = gh.git_checkout_branch("branch;rm -rf /")
        assert result.startswith("ERROR")

    def test_creates_new_branch(self, fake_workspace):
        with patch("subprocess.run", return_value=_make_proc(0, "", "")) as m:
            gh.git_checkout_branch("feature/my-branch", create=True)
        cmd = m.call_args[0][0]
        assert "-b" in cmd
        assert "feature/my-branch" in cmd

    def test_falls_back_if_branch_exists(self, fake_workspace):
        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if "-b" in cmd:
                return _make_proc(1, "", "fatal: A branch named 'x' already exists")
            return _make_proc(0, "", "")
        with patch("subprocess.run", side_effect=fake_run):
            result = gh.git_checkout_branch("x", create=True)
        assert len(calls) == 2
        assert "-b" not in calls[1]

    def test_checkout_only_when_create_false(self, fake_workspace):
        with patch("subprocess.run", return_value=_make_proc(0, "", "")) as m:
            gh.git_checkout_branch("main", create=False)
        cmd = m.call_args[0][0]
        assert "-b" not in cmd


# ---- git_commit -------------------------------------------------------------

class TestGitCommit:
    def test_rejects_empty_message(self):
        result = gh.git_commit("")
        assert result.startswith("ERROR")

    def test_rejects_blank_message(self):
        result = gh.git_commit("   ")
        assert result.startswith("ERROR")

    def test_stages_all_by_default(self, fake_workspace):
        cmds = []
        def fake_run(cmd, **kwargs):
            cmds.append(cmd)
            return _make_proc(0, "", "")
        with patch("subprocess.run", side_effect=fake_run):
            gh.git_commit("add feature")
        add_cmd = cmds[0]
        assert "add" in add_cmd
        assert "-A" in add_cmd

    def test_stages_specific_paths(self, fake_workspace):
        cmds = []
        def fake_run(cmd, **kwargs):
            cmds.append(cmd)
            return _make_proc(0, "", "")
        with patch("subprocess.run", side_effect=fake_run):
            gh.git_commit("fix bug", "src/a.py src/b.py")
        add_cmd = cmds[0]
        assert "src/a.py" in add_cmd
        assert "src/b.py" in add_cmd

    def test_commit_message_passed(self, fake_workspace):
        cmds = []
        def fake_run(cmd, **kwargs):
            cmds.append(cmd)
            return _make_proc(0, "1 file changed", "")
        with patch("subprocess.run", side_effect=fake_run):
            result = gh.git_commit("my commit message")
        commit_cmd = next(c for c in cmds if "commit" in c)
        assert "my commit message" in commit_cmd

    def test_stops_on_add_failure(self, fake_workspace):
        def fake_run(cmd, **kwargs):
            if "add" in cmd:
                return _make_proc(1, "", "error: pathspec 'missing.py' did not match")
            return _make_proc(0, "", "")
        with patch("subprocess.run", side_effect=fake_run):
            result = gh.git_commit("msg", "missing.py")
        assert "exit=1" in result


# ---- git_push ---------------------------------------------------------------

class TestGitPush:
    def test_token_injected_into_remote_url(self, fake_workspace, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_pushtoken")
        cmds = []
        def fake_run(cmd, **kwargs):
            cmds.append(cmd)
            if "get-url" in cmd:
                r = _make_proc(0, "https://github.com/owner/repo.git\n", "")
            else:
                r = _make_proc(0, "pushed", "")
            return r
        with patch("subprocess.run", side_effect=fake_run):
            gh.git_push("my-branch")
        set_url_cmd = next(c for c in cmds if "set-url" in c)
        assert "oauth2:ghp_pushtoken@" in " ".join(set_url_cmd)

    def test_token_stripped_from_output(self, fake_workspace, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret99")
        def fake_run(cmd, **kwargs):
            if "get-url" in cmd:
                return _make_proc(0, "https://github.com/owner/repo.git\n", "")
            return _make_proc(0, "https://oauth2:ghp_secret99@github.com/owner/repo.git", "")
        with patch("subprocess.run", side_effect=fake_run):
            result = gh.git_push()
        assert "ghp_secret99" not in result

    def test_original_url_restored_after_push(self, fake_workspace, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
        cmds = []
        def fake_run(cmd, **kwargs):
            cmds.append(list(cmd))
            if "get-url" in cmd:
                return _make_proc(0, "https://github.com/o/r.git\n", "")
            return _make_proc(0, "", "")
        with patch("subprocess.run", side_effect=fake_run):
            gh.git_push()
        # Last set-url call should restore the token-free URL
        set_url_calls = [c for c in cmds if "set-url" in c]
        assert len(set_url_calls) == 2
        last_url = set_url_calls[-1][-1]
        assert "oauth2" not in last_url


# ---- create_pull_request ----------------------------------------------------

class TestCreatePullRequest:
    def test_errors_without_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        result = gh.create_pull_request("Title", "Body", "feature-branch")
        assert "ERROR" in result
        assert "GITHUB_TOKEN" in result

    def test_auto_detects_repo_from_remote(self, fake_workspace, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_tok")
        captured_url = []
        def fake_run(cmd, **kwargs):
            if "get-url" in cmd:
                return _make_proc(0, "https://github.com/myorg/myrepo.git\n", "")
            return _make_proc(0, "", "")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"html_url": "https://github.com/myorg/myrepo/pull/1",
                                       "number": 1, "title": "Title"}
        with patch("subprocess.run", side_effect=fake_run):
            with patch("httpx.post", return_value=mock_resp) as mock_post:
                result = gh.create_pull_request("Title", "Body", "feature-branch")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["head"] == "feature-branch"
        assert payload["base"] == "main"

    def test_explicit_repo_used_directly(self, fake_workspace, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_tok")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"html_url": "https://github.com/o/r/pull/2",
                                       "number": 2, "title": "T"}
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = gh.create_pull_request("T", "B", "branch", repo="o/r")
        url = mock_post.call_args[0][0]
        assert "o/r" in url
        assert "PR created" in result

    def test_returns_pr_url_on_success(self, fake_workspace, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_tok")
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"html_url": "https://github.com/o/r/pull/42",
                                       "number": 42, "title": "My PR"}
        with patch("httpx.post", return_value=mock_resp):
            result = gh.create_pull_request("My PR", "desc", "branch", repo="o/r")
        assert "https://github.com/o/r/pull/42" in result
        assert "#42" in result

    def test_returns_error_on_api_failure(self, fake_workspace, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_tok")
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.text = "Validation Failed"
        with patch("httpx.post", return_value=mock_resp):
            result = gh.create_pull_request("T", "B", "branch", repo="o/r")
        assert "ERROR 422" in result

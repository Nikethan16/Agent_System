"""Tool-choice drift (#7): a BARE run_bash read/list/search is redirected to the dedicated tool
(read_file/list_files/grep/glob). A real pipeline/redirect/chain passes straight through, and the
whole thing is opt-out via AGENT_BASH_REDIRECT_TOOLS=0."""
import core.tools as tools


class _Out:
    returncode = 0
    stdout = "x"
    stderr = ""


def _redirect(cmd, monkeypatch):
    monkeypatch.delenv("AGENT_DISABLE_BASH", raising=False)
    monkeypatch.setenv("AGENT_BASH_REDIRECT_TOOLS", "1")
    return tools.run_bash(cmd)                 # drift redirect returns BEFORE the docker path


def test_bare_cat_redirects_to_read_file(monkeypatch):
    out = _redirect("cat backend/app/config.py", monkeypatch)
    assert out.startswith("BLOCKED") and "read_file" in out


def test_bare_head_tail_redirect(monkeypatch):
    assert "read_file" in _redirect("head -n 20 file.py", monkeypatch)
    assert "read_file" in _redirect("tail file.py", monkeypatch)


def test_bare_ls_redirects_to_list_files(monkeypatch):
    assert "list_files" in _redirect("ls -la src", monkeypatch)


def test_bare_grep_redirects(monkeypatch):
    assert "grep tool" in _redirect("grep -r TODO .", monkeypatch)


def test_find_redirects_to_glob(monkeypatch):
    assert "glob" in _redirect("find . -name '*.py'", monkeypatch)


def test_find_with_action_predicate_is_not_redirected(monkeypatch):
    # glob only enumerates — a find that DELETES or EXECs must reach the sandbox, not be redirected.
    monkeypatch.delenv("AGENT_DISABLE_BASH", raising=False)
    monkeypatch.setenv("AGENT_BASH_DOCKER_IMAGE", "test-img")
    monkeypatch.setattr(tools.subprocess, "run", lambda argv, **k: _Out())
    assert not tools.run_bash("find . -name '*.pyc' -delete").startswith("BLOCKED")
    assert not tools.run_bash("find . -name '*.py' -exec black {} +").startswith("BLOCKED")


def test_pipeline_is_not_redirected(monkeypatch):
    # A real pipeline is a genuine shell workflow -> must reach the sandbox, not a redirect.
    monkeypatch.delenv("AGENT_DISABLE_BASH", raising=False)
    monkeypatch.setenv("AGENT_BASH_DOCKER_IMAGE", "test-img")
    monkeypatch.setattr(tools.subprocess, "run", lambda argv, **k: _Out())
    out = tools.run_bash("cat foo.txt | wc -l")
    assert not out.startswith("BLOCKED")


def test_opt_out_disables_redirect(monkeypatch):
    monkeypatch.delenv("AGENT_DISABLE_BASH", raising=False)
    monkeypatch.setenv("AGENT_BASH_DOCKER_IMAGE", "test-img")
    monkeypatch.setenv("AGENT_BASH_REDIRECT_TOOLS", "0")
    monkeypatch.setattr(tools.subprocess, "run", lambda argv, **k: _Out())
    out = tools.run_bash("cat foo.txt")
    assert not out.startswith("BLOCKED")       # guard off -> reaches the sandbox


def test_running_a_real_command_is_not_redirected(monkeypatch):
    monkeypatch.delenv("AGENT_DISABLE_BASH", raising=False)
    monkeypatch.setenv("AGENT_BASH_DOCKER_IMAGE", "test-img")
    monkeypatch.setattr(tools.subprocess, "run", lambda argv, **k: _Out())
    out = tools.run_bash("python -m pytest -q")
    assert not out.startswith("BLOCKED")

"""Nikki-internal workspace artifacts (.skills/) must be excluded from the isolated work-copy's
git, so they can't land in the merge branch or the review diff and pollute the user's repo.
Found via dogfooding: a .skills/ dir appeared as `?? .skills/` in a review_merge diff."""
import subprocess

from server import isolation


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def _make_repo(copy):
    copy.mkdir(parents=True)
    _git(copy, "init")
    _git(copy, "config", "user.email", "t@t")
    _git(copy, "config", "user.name", "t")
    (copy / "a.txt").write_text("hi")
    _git(copy, "add", "-A")
    _git(copy, "commit", "-m", "init")


def test_skills_excluded_but_real_change_shown(tmp_path):
    ws = tmp_path / "workspaces"
    ws.mkdir()
    pid = "abc123"
    copy = ws / f"project_{pid}__work"
    _make_repo(copy)
    # A REAL edit + a Nikki-internal .skills/ dir the skills system would drop in.
    (copy / "a.txt").write_text("changed")
    (copy / ".skills" / "code-review").mkdir(parents=True)
    (copy / ".skills" / "code-review" / "SKILL.md").write_text("x")

    diff = isolation.diff_summary(pid, str(tmp_path / "real"), str(ws))
    assert "a.txt" in diff          # the genuine change is still surfaced
    assert ".skills" not in diff    # Nikki-internal is excluded
    assert isolation.has_changes(pid, str(tmp_path / "real"), str(ws))  # real change still detected


def test_only_skills_present_is_no_change(tmp_path):
    # If the ONLY thing in the work-copy is Nikki-internal, there's nothing to merge.
    ws = tmp_path / "workspaces"
    ws.mkdir()
    pid = "def456"
    copy = ws / f"project_{pid}__work"
    _make_repo(copy)
    (copy / ".skills" / "docx").mkdir(parents=True)
    (copy / ".skills" / "docx" / "SKILL.md").write_text("y")

    assert isolation.diff_summary(pid, str(tmp_path / "real"), str(ws)) == "(no changes)"
    assert not isolation.has_changes(pid, str(tmp_path / "real"), str(ws))

"""Skills Hub: enable/disable state, review-gate filtering, and allowlisted GitHub sync
(network mocked). A synced skill must land DISABLED and stay unselectable until enabled.
"""
import os
import json

import pytest

from core import skills as skill_lib
from core import skill_sync


@pytest.fixture()
def iso_skills(tmp_path):
    """Isolate the skills dir + state file so tests never touch the real ones. Restores
    the real skills registry (globals AND the loaded _SKILLS list) on teardown so a
    later test doesn't inherit this test's tmp skills."""
    orig = (skill_lib._DIR, skill_lib._STATE_PATH, skill_sync._SKILLS_DIR, skill_lib._SKILLS)
    sdir = tmp_path / "skills"
    sdir.mkdir()
    skill_lib._DIR = str(sdir)
    skill_lib._STATE_PATH = str(tmp_path / "skills_state.json")
    skill_sync._SKILLS_DIR = str(sdir)

    def make_skill(name, desc="a test skill"):
        d = sdir / name
        d.mkdir(exist_ok=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\nBody of {name}.", encoding="utf-8")

    try:
        yield sdir, make_skill
    finally:
        (skill_lib._DIR, skill_lib._STATE_PATH, skill_sync._SKILLS_DIR, skill_lib._SKILLS) = orig
        skill_lib.load()          # reload the real bundled skills for subsequent tests


def test_bundled_skill_enabled_by_default(iso_skills):
    _, make = iso_skills
    make("alpha")
    skill_lib.load()
    cat = {s["name"]: s for s in skill_lib.all_catalog()}
    assert cat["alpha"]["enabled"] is True


def test_disable_removes_from_selectable_catalog(iso_skills):
    _, make = iso_skills
    make("alpha", "make spreadsheets and reports")
    skill_lib.load()
    assert any(s["name"] == "alpha" for s in skill_lib.catalog())      # enabled -> in menu
    skill_lib.set_enabled("alpha", False)
    assert not any(s["name"] == "alpha" for s in skill_lib.catalog())  # gone from menu
    assert any(s["name"] == "alpha" for s in skill_lib.all_catalog())  # still visible to UI


def test_disabled_skill_not_selected(iso_skills):
    _, make = iso_skills
    make("reportskill", "generate a detailed report document")
    skill_lib.load()
    picked = skill_lib.select("please generate a detailed report", names=["reportskill"])
    assert [s.name for s in picked] == ["reportskill"]
    skill_lib.set_enabled("reportskill", False)
    # Even an EXPLICIT name request can't load a disabled skill (review gate).
    assert skill_lib.select("please generate a detailed report", names=["reportskill"]) == []


def test_state_persists_across_reload(iso_skills):
    _, make = iso_skills
    make("alpha")
    skill_lib.load()
    skill_lib.set_enabled("alpha", False)
    skill_lib.load()          # simulate a fresh process
    assert not any(s["name"] == "alpha" for s in skill_lib.catalog())


# ---- sync (GitHub mocked) ---------------------------------------------------
def test_sync_refuses_source_not_in_allowlist(iso_skills):
    with pytest.raises(ValueError, match="allowlist"):
        skill_sync.sync_skill("evil/repo", "whatever")


def test_sync_refuses_unsafe_skill_name(iso_skills, monkeypatch):
    monkeypatch.setattr(skill_sync, "_source",
                        lambda n: {"name": n, "repo": "anthropics/skills", "branch": "main", "path": ""})
    for bad in ("../etc", "a/b", ".hidden", "a\\b"):
        with pytest.raises(ValueError, match="unsafe"):
            skill_sync.sync_skill("anthropic-skills", bad)


def test_sync_writes_skill_and_marks_disabled(iso_skills, monkeypatch):
    sdir, _ = iso_skills
    monkeypatch.setattr(skill_sync, "_source",
                        lambda n: {"name": "anthropic-skills", "repo": "anthropics/skills",
                                   "branch": "main", "path": ""})

    # Fake the GitHub tree: one folder "docx" containing SKILL.md + scripts/gen.py.
    def fake_contents(repo, path, branch):
        if path == "docx":
            return [
                {"name": "SKILL.md", "type": "file", "path": "docx/SKILL.md",
                 "download_url": "u/SKILL.md"},
                {"name": "scripts", "type": "dir", "path": "docx/scripts"},
            ]
        if path == "docx/scripts":
            return [{"name": "gen.py", "type": "file", "path": "docx/scripts/gen.py",
                     "download_url": "u/gen.py"}]
        return []

    bodies = {"u/SKILL.md": b"---\nname: docx\ndescription: make word docs\n---\nBody.",
              "u/gen.py": b"print('hi')"}

    def fake_download(url, dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(bodies[url])

    monkeypatch.setattr(skill_sync, "_contents", fake_contents)
    monkeypatch.setattr(skill_sync, "_download", fake_download)

    result = skill_sync.sync_skill("anthropic-skills", "docx")
    assert result["files"] == 2 and result["enabled"] is False
    # Files landed in the right place, preserving the subfolder.
    assert (sdir / "docx" / "SKILL.md").is_file()
    assert (sdir / "docx" / "scripts" / "gen.py").is_file()
    # And it's DISABLED — not selectable until reviewed + enabled.
    assert not any(s["name"] == "docx" for s in skill_lib.catalog())
    state = json.load(open(sdir.parent / "skills_state.json", encoding="utf-8"))
    assert state["docx"] is False


def test_sync_rejects_missing_skill_md(iso_skills, monkeypatch):
    monkeypatch.setattr(skill_sync, "_source",
                        lambda n: {"name": "anthropic-skills", "repo": "anthropics/skills",
                                   "branch": "main", "path": ""})
    monkeypatch.setattr(skill_sync, "_contents",
                        lambda repo, path, branch: [{"name": "readme.md", "type": "file",
                                                     "path": "x/readme.md", "download_url": "u/r"}])

    def fake_dl(url, dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w") as f:
            f.write("x")

    monkeypatch.setattr(skill_sync, "_download", fake_dl)
    with pytest.raises(ValueError, match="no SKILL.md"):
        skill_sync.sync_skill("anthropic-skills", "x")

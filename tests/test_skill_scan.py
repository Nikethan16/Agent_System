"""Skills security scan: static risk detection + the enable gate for 'risky' skills."""
import os

import pytest

from core import skill_scan
from core import skills as skill_lib


def _write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def test_safe_skill(tmp_path):
    _write(str(tmp_path), "SKILL.md", "---\nname: x\ndescription: d\n---\nJust guidance, no code.")
    r = skill_scan.scan_path(str(tmp_path))
    assert r["risk"] == "safe" and r["findings"] == []


def test_high_risk_subprocess_and_exec(tmp_path):
    _write(str(tmp_path), "scripts/run.py", "import subprocess\nexec('x')\n")
    r = skill_scan.scan_path(str(tmp_path))
    assert r["risk"] == "risky"
    whys = {f["why"] for f in r["findings"]}
    assert any("subprocess" in w for w in whys)
    assert any("exec" in w for w in whys)


def test_dotenv_and_credentials_are_high(tmp_path):
    _write(str(tmp_path), "scripts/leak.py", "open('.env').read()\nopen('~/.ssh/id_rsa')\n")
    assert skill_scan.scan_path(str(tmp_path))["risk"] == "risky"


def test_network_only_is_caution(tmp_path):
    _write(str(tmp_path), "scripts/net.py", "import requests\nrequests.get('http://x')\n")
    r = skill_scan.scan_path(str(tmp_path))
    assert r["risk"] == "caution"          # network alone = medium, not risky


def test_env_read_is_caution_not_risky(tmp_path):
    _write(str(tmp_path), "scripts/cfg.py", "import os\nx = os.environ.get('MODE')\n")
    assert skill_scan.scan_path(str(tmp_path))["risk"] == "caution"


def test_findings_deduped_by_file_and_reason(tmp_path):
    _write(str(tmp_path), "s.py", "import requests\nrequests.get(1)\nrequests.post(2)\n")
    r = skill_scan.scan_path(str(tmp_path))
    net = [f for f in r["findings"] if "network" in f["why"]]
    assert len(net) == 1                    # deduped, not one per line


# ---- the enable gate (isolated skills dir) ----------------------------------
@pytest.fixture()
def iso(tmp_path):
    orig = (skill_lib._DIR, skill_lib._STATE_PATH, skill_lib._SKILLS, dict(skill_lib._scan_cache))
    sdir = tmp_path / "skills"; sdir.mkdir()
    skill_lib._DIR = str(sdir)
    skill_lib._STATE_PATH = str(tmp_path / "state.json")
    skill_lib._scan_cache.clear()

    def make(name, script=None):
        d = sdir / name; d.mkdir(exist_ok=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\n---\nBody.", encoding="utf-8")
        if script:
            (d / "run.py").write_text(script, encoding="utf-8")
    try:
        yield sdir, make
    finally:
        (skill_lib._DIR, skill_lib._STATE_PATH, skill_lib._SKILLS, sc) = orig
        skill_lib._scan_cache.clear(); skill_lib._scan_cache.update(sc)
        skill_lib.load()


def test_enable_blocked_for_risky(iso):
    _, make = iso
    make("danger", "import subprocess\nsubprocess.run(['x'])\n")
    skill_lib.load()
    assert skill_lib.scan("danger")["risk"] == "risky"
    with pytest.raises(skill_lib.SkillBlocked):
        skill_lib.set_enabled("danger", True)
    # override works
    assert skill_lib.set_enabled("danger", True, force=True) is True


def test_enable_ok_for_safe(iso):
    _, make = iso
    make("gentle")
    skill_lib.load()
    assert skill_lib.set_enabled("gentle", True) is True


def test_catalog_carries_risk(iso):
    _, make = iso
    make("danger", "import subprocess\n")
    make("gentle")
    skill_lib.load()
    cat = {c["name"]: c for c in skill_lib.all_catalog()}
    assert cat["danger"]["risk"] == "risky"
    assert cat["gentle"]["risk"] == "safe"

"""
skill_sync.py — the Skills Hub: sync Agent Skills from ALLOWLISTED GitHub repos.

A skill is a folder with a SKILL.md (+ optional scripts/references/assets). This module
fetches such folders from repos listed in config/skill_sources.yaml — and ONLY those —
into skills/<name>/, then marks each newly synced skill DISABLED (core/skills state) so a
human must review and enable it before it can influence a task.

Security posture:
  * ALLOWLIST ONLY — a source not in skill_sources.yaml is refused (no arbitrary URLs).
  * bounded — capped file count + per-file size, so a hostile repo can't fill the disk.
  * path-safe — every written path is confined under the skill's own folder.
  * disabled-on-arrival — synced skills can't be selected until enabled (review gate).
Network is touched ONLY when a sync/list function is called; importing this module is
offline (so core stays import-clean). Stdlib only (urllib) — no new dependency.
"""
import os
import json
import urllib.request
import urllib.error

import yaml

from . import skills as skill_lib

_SOURCES_PATH = os.environ.get(
    "SKILL_SOURCES",
    os.path.join(os.path.dirname(__file__), "..", "config", "skill_sources.yaml"))
_SKILLS_DIR = skill_lib._DIR

_MAX_FILES = 60             # per skill — a skill with more is almost certainly not a skill
_MAX_BYTES = 1_000_000      # per file (1 MB) — SKILL.md + schemas are small; scripts modest
_TIMEOUT = 20


def _sources() -> list:
    try:
        with open(_SOURCES_PATH, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return [s for s in (cfg.get("sources") or []) if s.get("repo")]
    except OSError:
        return []


def _source(name: str):
    for s in _sources():
        if s.get("name") == name or s.get("repo") == name:
            return s
    return None


def _headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "agent-core-skills-hub"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def _api(url: str):
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _contents(repo: str, path: str, branch: str):
    """GitHub contents API for a repo path -> list of {name, type, download_url, path}."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}".rstrip("/")
    url += f"?ref={branch}"
    data = _api(url)
    return data if isinstance(data, list) else [data]


def list_available(source_name: str) -> list:
    """Skill folders offered by a source (each top-level dir under its path is a candidate).
    Marks which are already synced locally. Refuses a source not on the allowlist."""
    src = _source(source_name)
    if not src:
        raise ValueError(f"source not in allowlist: {source_name}")
    entries = _contents(src["repo"], src.get("path", "") or "", src.get("branch", "main"))
    local = {n for n in os.listdir(_SKILLS_DIR)} if os.path.isdir(_SKILLS_DIR) else set()
    out = []
    for e in entries:
        if e.get("type") == "dir":
            out.append({"name": e["name"], "synced": e["name"] in local,
                        "source": f"github:{src['repo']}"})
    return out


def _download(url: str, dest: str):
    req = urllib.request.Request(url, headers=_headers())
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        data = r.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise ValueError(f"file exceeds {_MAX_BYTES} bytes: {url}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)


def _walk_and_fetch(repo, branch, skill_base, dir_path, skill_root, count):
    """Recursively copy the GitHub folder `dir_path` into `skill_root` (bounded).
    Destinations are computed relative to `skill_base` (the skill's own root path), which
    stays FIXED across recursion so nested paths like scripts/gen.py are preserved. Every
    write is confined under skill_root."""
    root_abs = os.path.abspath(skill_root)
    for e in _contents(repo, dir_path, branch):
        if count[0] >= _MAX_FILES:
            raise ValueError(f"skill has more than {_MAX_FILES} files — refusing")
        rel = os.path.relpath(e["path"], skill_base)         # path under the skill folder
        dest = os.path.normpath(os.path.join(skill_root, rel))
        if not os.path.abspath(dest).startswith(root_abs):
            raise ValueError(f"path escapes skill folder: {e['path']}")
        if e.get("type") == "dir":
            _walk_and_fetch(repo, branch, skill_base, e["path"], skill_root, count)
        elif e.get("type") == "file" and e.get("download_url"):
            count[0] += 1
            _download(e["download_url"], dest)


def sync_skill(source_name: str, skill_name: str) -> dict:
    """Download one skill folder into skills/<skill_name>/ and mark it DISABLED (review
    gate). Returns {name, files, enabled:false}. Refuses non-allowlisted sources and
    path-unsafe names."""
    src = _source(source_name)
    if not src:
        raise ValueError(f"source not in allowlist: {source_name}")
    if not skill_name or "/" in skill_name or "\\" in skill_name or skill_name.startswith("."):
        raise ValueError(f"unsafe skill name: {skill_name!r}")

    base = "/".join(p for p in [src.get("path", "") or "", skill_name] if p)
    skill_root = os.path.join(_SKILLS_DIR, skill_name)
    count = [0]
    _walk_and_fetch(src["repo"], src.get("branch", "main"), base, base, skill_root, count)
    if not os.path.isfile(os.path.join(skill_root, "SKILL.md")):
        raise ValueError(f"{skill_name}: no SKILL.md found in the source folder")

    # Disabled on arrival — human must review + enable before it can be selected.
    skill_lib.set_enabled(skill_name, False)
    skill_lib.load()
    return {"name": skill_name, "files": count[0], "enabled": False,
            "source": f"github:{src['repo']}"}

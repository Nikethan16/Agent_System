"""
skills.py — Agent Skills (Claude-style). A skill is a folder under skills/<name>/ with
a SKILL.md (YAML frontmatter `name` + `description`, optional `keywords`/`agents`, then a
markdown body of instructions) and optional scripts/references/assets.

Progressive disclosure:
  1. metadata (name + description) is always cheap to scan — used to pick relevant skills;
  2. the full SKILL.md body is injected into an agent ONLY when its skill is selected;
  3. bundled scripts/resources are staged into the workspace so the agent can run them.

Drop in any skill from github.com/anthropics/skills (or your own) — just copy the folder
into skills/. No code change needed.
"""
import os
import re
import json
import shutil
import threading

import yaml

from .tools import current_workspace

_DIR = os.environ.get("SKILLS_DIR", os.path.join(os.path.dirname(__file__), "..", "skills"))
_WORD = re.compile(r"[a-z0-9]+")

# Enable/disable + provenance state for the Skills Hub. Skills synced from GitHub
# (skill_sync) land DISABLED and must be reviewed + enabled by a human before they can
# influence a task — a skill body is injected as agent guidance, so an unvetted one is
# an instruction-injection vector. Bundled repo skills (no state entry) default ENABLED.
_STATE_PATH = os.environ.get(
    "SKILLS_STATE",
    os.path.join(os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data")),
                 "skills_state.json"))
_state_lock = threading.Lock()


def _load_state() -> dict:
    try:
        with open(_STATE_PATH, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict):
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


class Skill:
    def __init__(self, path, meta, body):
        self.path = path
        self.name = meta.get("name") or os.path.basename(path)
        self.description = meta.get("description", "")
        self.keywords = [str(k).lower() for k in (meta.get("keywords") or [])]
        self.agents = meta.get("agents") or []        # restrict to these agent ids (optional)
        self.body = body
        self.enabled = True         # set from state in load()
        self.source = meta.get("source", "")          # e.g. "github:anthropics/skills" if synced


def _parse(skill_md: str) -> Skill:
    text = open(skill_md, encoding="utf-8").read()
    meta, body = {}, text
    if text.lstrip().startswith("---"):
        try:
            _, fm, body = text.split("---", 2)
            meta = yaml.safe_load(fm) or {}
        except Exception:
            meta, body = {}, text
    return Skill(os.path.dirname(skill_md), meta, body.strip())


_SKILLS: list = []


def load():
    global _SKILLS
    out = []
    state = _load_state()
    if os.path.isdir(_DIR):
        for name in sorted(os.listdir(_DIR)):
            md = os.path.join(_DIR, name, "SKILL.md")
            if os.path.isfile(md):
                try:
                    s = _parse(md)
                    # Bundled skills (no state entry) default enabled; synced skills are
                    # written into state as False on sync until a human reviews + enables.
                    s.enabled = bool(state.get(s.name, True))
                    # Provenance sidecar (written by skill_sync) marks a GitHub-synced skill.
                    src_file = os.path.join(os.path.dirname(md), ".source")
                    if os.path.isfile(src_file):
                        try:
                            with open(src_file, encoding="utf-8") as sf:
                                s.source = sf.read().strip() or s.source
                        except OSError:
                            pass
                    out.append(s)
                except Exception:
                    pass
    _SKILLS = out
    _scan_cache.clear()          # skills changed -> re-scan lazily
    return out


# Security-scan cache, keyed by skill path (skills change rarely; scanning the docx/pptx
# schema bundles every list call would be wasteful). Cleared on load().
_scan_cache: dict = {}


def scan(name: str) -> dict:
    """The security scan for a skill (cached). {risk: safe|caution|risky, findings, scanned}."""
    from . import skill_scan
    s = get(name)
    if not s:
        return {"risk": "safe", "findings": [], "scanned": 0}
    if s.path not in _scan_cache:
        _scan_cache[s.path] = skill_scan.scan_skill(s)
    return _scan_cache[s.path]


class SkillBlocked(Exception):
    """Raised when enabling a skill the scan flags 'risky' without an override."""


def set_enabled(name: str, enabled: bool, force: bool = False) -> bool:
    """Enable/disable a skill (persisted). ENABLING a skill the scanner flags 'risky' is
    BLOCKED unless force=True — the security gate on top of the review gate. Returns the
    new state."""
    if enabled and not force and scan(name).get("risk") == "risky":
        raise SkillBlocked(
            f"'{name}' has HIGH-risk findings — review them, then enable with override if intended.")
    with _state_lock:
        state = _load_state()
        state[name] = bool(enabled)
        _save_state(state)
    for s in _SKILLS:
        if s.name == name:
            s.enabled = bool(enabled)
    return bool(enabled)


def all_catalog() -> list:
    """Every skill (enabled AND disabled) with its state, source + security scan — for the
    Skills tab. (catalog() below returns only ENABLED skills, for the lead's menu.)"""
    out = []
    for s in _SKILLS:
        sc = scan(s.name)
        out.append({"name": s.name, "description": s.description,
                    "enabled": s.enabled, "source": s.source,
                    "has_scripts": os.path.isdir(os.path.join(s.path, "scripts")),
                    "risk": sc["risk"], "findings": len(sc["findings"])})
    return out


load()


# Generic words that shouldn't drive skill selection (so distinctive words like
# "spreadsheet" or "powerpoint" decide the match, not "create"/"me"/"a").
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "me",
    "my", "i", "you", "it", "this", "that", "is", "are", "be", "please", "can",
    "could", "would", "want", "need", "make", "create", "build", "write", "give",
    "get", "do", "use", "using", "into", "from", "as", "at", "by", "new", "some",
    "about", "should", "we", "us", "out", "up", "then", "so", "have", "has",
}
# High-signal trigger words → skill name, for short prompts where description
# overlap alone is thin (e.g. "make a deck" → pptx).
_SIGNALS = {
    "xlsx": ("spreadsheet", "excel", "xlsx", "workbook", "worksheet", "sheet", "csv"),
    "docx": ("docx", "word", "letter", "memo", "letterhead"),
    "pptx": ("powerpoint", "pptx", "slide", "slides", "deck", "presentation"),
    "pdf": ("pdf",),
    # web-frontend is also intent-gated (added 2026-07-12): it kept firing on backend/CLI/library tasks (a
    # bank module, a bare `echo`) on generic word overlap. Only fire when the task is
    # actually about a web UI, not any task that happens to share a couple of dev words.
    "web-frontend": ("html", "css", "frontend", "front-end", "webpage", "web page",
                     "website", "landing page", "responsive", "browser", "ui ", "dom"),
}

# The document-format skills bundle ~1MB of Office XML schemas + generator scripts and get
# STAGED into the workspace on selection. Only auto-load them for an agent that can actually
# RUN those scripts (has run_bash) — otherwise a text-only agent (research/general) that just
# mentions "spreadsheet/csv" in passing pulls in the whole payload for nothing (observed live
# 2026-07-12: a JSON-export research step dumped ~50 xlsx schema files into the workspace).
_DOC_FORMAT_SKILLS = {"xlsx", "docx", "pptx", "pdf"}


def catalog() -> list:
    """Always-cheap metadata (the progressive-disclosure layer 1) — ENABLED skills only,
    so a synced-but-unreviewed skill is never offered to the lead."""
    return [{"name": s.name, "description": s.description} for s in _SKILLS if s.enabled]


def get(name: str):
    for s in _SKILLS:
        if s.name == name:
            return s
    return None


def _enabled_skills() -> list:
    return [s for s in _SKILLS if s.enabled]


def _score(task_words: set, raw_task: str, s: Skill) -> int:
    sigs = _SIGNALS.get(s.name)
    if sigs is not None:
        # Document-FORMAT skills (docx/pptx/xlsx/pdf) are intent-GATED: they bundle
        # heavy machinery (≈1MB of XML schemas) and must only fire when the user
        # actually wants that file format — never on generic description overlap like
        # "document"/"report"/"README". Match on a distinctive format word only, with a
        # word boundary so "password"/"keyword" can't trigger "word", etc.
        # Whole-word match (leading AND trailing \b): without the trailing boundary a
        # signal was a PREFIX match, so "memo" fired docx on "memoize", "word" on "wording",
        # etc. (observed live: a memoize-cache task pulled in the whole docx skill).
        hits = sum(1 for sig in sigs
                   if re.search(r"\b" + re.escape(sig.strip()) + r"\b", raw_task))
        return (2 + hits) if hits else 0
    hay = set((s.name or "").lower().replace("-", " ").split())
    hay |= set(s.keywords)
    hay |= (set(_WORD.findall((s.description or "").lower())) - _STOP)
    return len(task_words & hay)


def select(task: str, agent=None, k: int = 2, min_score: int = 2, names=None,
           auto: bool = True) -> list:
    """Pick the most relevant skills for a task.

    Deterministic and free (no model call). `names` force-loads specific skills the
    caller already chose (Claude-style explicit selection by the lead agent) — those
    are returned first, then auto-matched ones fill the remaining slots.

    `auto=False` disables fuzzy auto-matching (only explicit `names` load). The
    orchestrator uses this for trivial tier-1 tasks so a one-line factual question
    can't drag in a heavy skill like the research report (orchestration issue #5).
    """
    raw = (task or "").lower()
    tw = set(_WORD.findall(raw)) - _STOP
    if agent is not None:
        tw |= set(str(c).lower() for c in getattr(agent, "capabilities", []) or [])

    # Only ENABLED skills are selectable — a synced skill can't influence a task until a
    # human has reviewed and enabled it (even if the lead explicitly names it).
    pool = _enabled_skills()

    forced = []
    if names:
        wanted = {str(n).strip().lower() for n in names}
        forced = [s for s in pool if s.name.lower() in wanted]

    if not auto:
        return forced[:max(k, len(forced))] if forced else []

    cands = []
    for s in pool:
        if s in forced:
            continue
        if s.agents and agent is not None and agent.id not in s.agents:
            continue
        # Don't auto-load (and stage) a heavy doc-format skill for an agent that can't run
        # its generator scripts. Explicit `names=` from the lead still override this.
        if (s.name in _DOC_FORMAT_SKILLS and agent is not None
                and "run_bash" not in set(getattr(agent, "tools", None) or [])):
            continue
        sc = _score(tw, raw, s)
        if sc >= min_score:
            cands.append((sc, s))
    cands.sort(key=lambda x: -x[0])
    auto = [s for _, s in cands]
    return (forced + auto)[:max(k, len(forced))]


def context(skills: list) -> str:
    """The full instructions of the selected skills (progressive-disclosure layer 2)."""
    if not skills:
        return ""
    parts = [f"### Skill: {s.name}\n{s.body}" for s in skills]
    return ("You have relevant SKILLS below — follow their guidance to produce "
            "high-quality output. Bundled scripts (if any) are in ./.skills/<name>/.\n\n" +
            "\n\n".join(parts))


def stage(skills: list):
    """Copy a skill's bundled scripts/resources into the workspace (layer 3).

    Idempotent: a skill's files are copied into a session's workspace at most once
    (some skills — docx/xlsx/pptx — bundle ~1MB of XML schemas, so re-copying every
    turn would be wasteful). A staged marker dir means "already done, skip".
    """
    base = os.path.join(current_workspace(), ".skills")
    for s in skills:
        skill_root = os.path.join(base, s.name)
        if os.path.isdir(skill_root):
            continue  # already staged for this session
        staged_any = False
        for sub in ("scripts", "references", "assets"):
            src = os.path.join(s.path, sub)
            if os.path.isdir(src):
                dst = os.path.join(skill_root, sub)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)
                staged_any = True
        # Also stage LOOSE top-level reference files the SKILL.md body points to
        # (e.g. pdf/REFERENCE.md, pdf/FORMS.md, pptx/EDITING.md) — they live next to
        # SKILL.md, not in a subfolder, so the agent can read them from ./.skills/<name>/.
        for fn in os.listdir(s.path):
            fp = os.path.join(s.path, fn)
            if not os.path.isfile(fp):
                continue
            if fn == "SKILL.md" or fn.lower().startswith("license"):
                continue
            os.makedirs(skill_root, exist_ok=True)
            shutil.copy2(fp, os.path.join(skill_root, fn))
            staged_any = True
        if not staged_any:
            # No bundled files — still drop a marker so we don't re-scan each turn.
            os.makedirs(skill_root, exist_ok=True)

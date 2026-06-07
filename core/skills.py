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
import shutil

import yaml

from .tools import current_workspace

_DIR = os.environ.get("SKILLS_DIR", os.path.join(os.path.dirname(__file__), "..", "skills"))
_WORD = re.compile(r"[a-z0-9]+")


class Skill:
    def __init__(self, path, meta, body):
        self.path = path
        self.name = meta.get("name") or os.path.basename(path)
        self.description = meta.get("description", "")
        self.keywords = [str(k).lower() for k in (meta.get("keywords") or [])]
        self.agents = meta.get("agents") or []        # restrict to these agent ids (optional)
        self.body = body


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
    if os.path.isdir(_DIR):
        for name in sorted(os.listdir(_DIR)):
            md = os.path.join(_DIR, name, "SKILL.md")
            if os.path.isfile(md):
                try:
                    out.append(_parse(md))
                except Exception:
                    pass
    _SKILLS = out
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
}


def catalog() -> list:
    """Always-cheap metadata (the progressive-disclosure layer 1)."""
    return [{"name": s.name, "description": s.description} for s in _SKILLS]


def get(name: str):
    for s in _SKILLS:
        if s.name == name:
            return s
    return None


def _score(task_words: set, raw_task: str, s: Skill) -> int:
    sigs = _SIGNALS.get(s.name)
    if sigs is not None:
        # Document-FORMAT skills (docx/pptx/xlsx/pdf) are intent-GATED: they bundle
        # heavy machinery (≈1MB of XML schemas) and must only fire when the user
        # actually wants that file format — never on generic description overlap like
        # "document"/"report"/"README". Match on a distinctive format word only, with a
        # word boundary so "password"/"keyword" can't trigger "word", etc.
        hits = sum(1 for sig in sigs if re.search(r"\b" + re.escape(sig), raw_task))
        return (2 + hits) if hits else 0
    hay = set((s.name or "").lower().replace("-", " ").split())
    hay |= set(s.keywords)
    hay |= (set(_WORD.findall((s.description or "").lower())) - _STOP)
    return len(task_words & hay)


def select(task: str, agent=None, k: int = 2, min_score: int = 2, names=None) -> list:
    """Pick the most relevant skills for a task.

    Deterministic and free (no model call). `names` force-loads specific skills the
    caller already chose (Claude-style explicit selection by the lead agent) — those
    are returned first, then auto-matched ones fill the remaining slots.
    """
    raw = (task or "").lower()
    tw = set(_WORD.findall(raw)) - _STOP
    if agent is not None:
        tw |= set(str(c).lower() for c in getattr(agent, "capabilities", []) or [])

    forced = []
    if names:
        wanted = {str(n).strip().lower() for n in names}
        forced = [s for s in _SKILLS if s.name.lower() in wanted]

    cands = []
    for s in _SKILLS:
        if s in forced:
            continue
        if s.agents and agent is not None and agent.id not in s.agents:
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

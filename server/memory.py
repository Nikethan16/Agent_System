"""
memory.py — cross-session memory (roadmap #1), now embedding-capable.

Persists a short record of each turn and recalls the most relevant past notes when a
new turn starts. Retrieval uses VECTOR EMBEDDINGS when an embedding model is configured
(`embed_model:` in config/models.yaml or EMBED_MODEL in .env), and transparently falls
back to an OFFLINE lexical scorer otherwise — so it works with zero setup and upgrades
automatically when you add an embedding model + key (see docs/PLACEHOLDERS.md).
"""
import os
import re
import json
import math
import logging

from sqlmodel import SQLModel, Field, Session as DBSession, select

from .db import engine, _uuid, _now

log = logging.getLogger(__name__)

# Cap how many recent notes a single recall scans. Without this, every turn loads
# the ENTIRE memory table and scores it in Python — O(N) and unbounded as history
# grows. Scanning the most-recent slice keeps recall fast and recency-relevant.
# (The roadmap's vector store would replace this with a real index.)
_MAX_SCAN = int(os.environ.get("MEMORY_MAX_SCAN", "2000"))
# Cosine-similarity cutoff for embedding-based recall (Phase C). Tunable without code.
_SEMANTIC_THRESHOLD = float(os.environ.get("MEMORY_SEMANTIC_THRESHOLD", "0.60"))

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "and", "for", "with", "that", "this", "you", "are", "was", "but",
         "has", "have", "from", "your", "out", "use", "can", "will", "what", "how"}


class Memory(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(default="", index=True)
    kind: str = "turn"           # turn (episodic) | fact (semantic) | summary (working)
    text: str = ""
    embedding: str = ""          # JSON-encoded vector when embeddings are configured
    scope: str = Field(default="", index=True)   # global | project:<id> | session:<id>
    fact_key: str = ""           # dedupe key for facts (e.g. "language", "tone_pref")
    updated_at: str = Field(default_factory=_now)
    created_at: str = Field(default_factory=_now)


# ---- embedding backend (optional) ------------------------------------------
def _embed_model():
    try:
        from core.registry import registry
        return registry.cfg.get("embed_model") or os.environ.get("EMBED_MODEL")
    except Exception:
        return os.environ.get("EMBED_MODEL")


def _vec(text: str):
    model = _embed_model()
    if not model:
        return None
    try:
        from core.llm import embed, Budget
        v, _ = embed(text, model, budget=Budget(max_usd=0.05, max_iterations=2))
        return v
    except Exception:
        return None


def _cos(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ---- lexical backend (always available, offline) ---------------------------
def _tokens(s: str):
    return [w for w in _WORD.findall((s or "").lower()) if len(w) > 2 and w not in _STOP]


def _lex(query_tokens: set, doc_tokens: set) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    inter = len(query_tokens & doc_tokens)
    return inter / (math.sqrt(len(query_tokens)) * math.sqrt(len(doc_tokens)))


# ---- public API -------------------------------------------------------------
def remember(text: str, session_id: str = "", kind: str = "turn", scope: str = "") -> None:
    if not text or not text.strip():
        return
    vec = _vec(text)
    with DBSession(engine) as s:
        s.add(Memory(session_id=session_id, kind=kind, text=text[:2000],
                     scope=scope, embedding=json.dumps(vec) if vec else ""))
        s.commit()
    try:
        from . import vectorstore
        vectorstore.on_write()
    except Exception:
        pass


def recall(query: str, k: int = 3, min_score: float = 0.12, exclude_session: str = None,
           scope_hint: str = None) -> list:
    """Top-k relevant past notes (episodic). Uses embeddings if configured, else lexical.
    `scope_hint` (e.g. 'project:<id>') gently boosts notes from the SAME project so a
    project's own history is preferred over unrelated global notes.

    When an embedding model is configured, tries the NumPy vector index first (fast,
    full-corpus search — no _MAX_SCAN ceiling). Falls back to the Python cosine loop,
    then to lexical if nothing matches."""
    def _boost(text_or_scope, sc):
        return sc + (0.08 if scope_hint and text_or_scope == scope_hint else 0.0)

    if _embed_model():
        qv = _vec(query)
        if qv:
            # Fast path: NumPy vectorstore (full-corpus, no _MAX_SCAN ceiling)
            try:
                from . import vectorstore
                hits = vectorstore.search(qv, k * 2, kind="turn",
                                          threshold=_SEMANTIC_THRESHOLD)
                if hits:
                    # Re-apply scope boost. We need the scope for each hit;
                    # look it up in a single batch query by text (good enough at this scale).
                    if scope_hint:
                        with DBSession(engine) as s:
                            scope_map = {
                                m.text: m.scope
                                for m in s.exec(
                                    select(Memory).where(Memory.kind == "turn")
                                ).all()
                                if m.text
                            }
                    else:
                        scope_map = {}
                    boosted = [(_boost(scope_map.get(t, ""), sc), t)
                               for sc, t in hits]
                    boosted.sort(key=lambda x: -x[0])
                    return [t for _, t in boosted[:k]]
            except Exception:
                pass  # fall through to legacy Python loop

            # Legacy Python loop (bounded by _MAX_SCAN for backward compat)
            with DBSession(engine) as s:
                rows = s.exec(
                    select(Memory).order_by(Memory.created_at.desc()).limit(_MAX_SCAN)
                ).all()
            rows = [m for m in rows
                    if m.kind == "turn" and not (exclude_session and m.session_id == exclude_session)]
            if rows:
                scored = []
                for m in rows:
                    if not m.embedding:
                        continue
                    try:
                        sc = _cos(qv, json.loads(m.embedding))
                    except Exception:
                        continue
                    if sc >= _SEMANTIC_THRESHOLD:
                        scored.append((_boost(m.scope, sc), m.text))
                if scored:
                    scored.sort(key=lambda x: -x[0])
                    return [t for _, t in scored[:k]]
                # fall through to lexical
            else:
                rows = []
        else:
            rows = None
    else:
        rows = None

    # Lexical fallback (offline, always available)
    if rows is None:
        with DBSession(engine) as s:
            rows = s.exec(
                select(Memory).order_by(Memory.created_at.desc()).limit(_MAX_SCAN)
            ).all()
        rows = [m for m in rows
                if m.kind == "turn" and not (exclude_session and m.session_id == exclude_session)]
    if not rows:
        return []
    q = set(_tokens(query))
    if not q:
        return []
    scored = [(_boost(m.scope, s), m.text) for m in rows
              for s in [_lex(q, set(_tokens(m.text)))] if s >= min_score]
    scored.sort(key=lambda x: -x[0])
    return [t for _, t in scored[:k]]


def prune(max_turns: int = None) -> int:
    """Delete the oldest episodic 'turn' notes beyond a cap so memory doesn't grow
    without bound (facts/rules/state/summary are durable and never pruned here).
    Best-effort; returns how many were removed."""
    cap = max_turns or int(os.environ.get("MEMORY_MAX_TURNS", "5000"))
    deleted = 0
    with DBSession(engine) as s:
        turns = s.exec(
            select(Memory).where(Memory.kind == "turn").order_by(Memory.created_at.desc())
        ).all()
        for m in turns[cap:]:
            s.delete(m)
            deleted += 1
        if deleted:
            s.commit()
    if deleted:
        try:
            from . import vectorstore
            vectorstore.on_write()
        except Exception:
            pass
    return deleted


# ===========================================================================
#  PROJECT / THREAD STATE — a structured, resumable roadmap (Phase 3).
#  Unlike the lossy free-text summary, this is an explicit { goal, plan[], next,
#  artifacts[] } record, re-injected at the TOP of every turn so work CONTINUES
#  exactly where it stopped — even in a NEW chat within the same project
#  ("we finished phase 2 → now do phase 3"). One row per scope (kind="state").
# ===========================================================================
def get_state(scope: str) -> dict:
    if not scope:
        return {}
    with DBSession(engine) as s:
        row = s.exec(
            select(Memory).where(Memory.kind == "state", Memory.scope == scope)
        ).first()
    if not row or not row.text:
        return {}
    try:
        return json.loads(row.text)
    except Exception:
        return {}


def set_state(scope: str, state: dict) -> None:
    if not scope or not isinstance(state, dict):
        return
    blob = json.dumps(state)[:8000]
    with DBSession(engine) as s:
        row = s.exec(
            select(Memory).where(Memory.kind == "state", Memory.scope == scope)
        ).first()
        if row:
            row.text, row.updated_at = blob, _now()
        else:
            row = Memory(kind="state", scope=scope, text=blob, updated_at=_now())
        s.add(row)
        s.commit()


def clear_state(scope: str) -> bool:
    with DBSession(engine) as s:
        row = s.exec(
            select(Memory).where(Memory.kind == "state", Memory.scope == scope)
        ).first()
        if not row:
            return False
        s.delete(row)
        s.commit()
        return True


def state_context(scope: str) -> str:
    """Render the saved roadmap as a RESUME block for the top of the context."""
    st = get_state(scope)
    if not st:
        return ""
    lines = []
    if st.get("goal"):
        lines.append(f"Goal: {st['goal']}")
    plan = st.get("plan") or []
    if plan:
        mark = {"done": "[x]", "in_progress": "[~]"}
        lines.append("Roadmap progress:")
        lines += [f"  {mark.get(t.get('status'), '[ ]')} {t.get('text', '')}" for t in plan[:25]]
    if st.get("next"):
        lines.append("Next up: " + st["next"])
    if st.get("artifacts"):
        lines.append("Files produced so far: " + ", ".join(st["artifacts"][:25]))
    body = "\n".join(lines)
    return ("RESUME — you are continuing ongoing work. Pick up from the roadmap below; "
            "do NOT restart from scratch:\n" + body) if body else ""


# ===========================================================================
#  WORKING MEMORY — a rolling per-session summary of older turns
#  (so a long chat keeps its thread once it grows past the verbatim window).
# ===========================================================================
def get_summary(session_id: str) -> str:
    with DBSession(engine) as s:
        row = s.exec(
            select(Memory).where(Memory.session_id == session_id, Memory.kind == "summary")
        ).first()
        return row.text if row else ""


def set_summary(session_id: str, text: str) -> None:
    with DBSession(engine) as s:
        row = s.exec(
            select(Memory).where(Memory.session_id == session_id, Memory.kind == "summary")
        ).first()
        if row:
            row.text, row.updated_at = text[:4000], _now()
        else:
            row = Memory(session_id=session_id, kind="summary", text=text[:4000],
                         scope=f"session:{session_id}", updated_at=_now())
        s.add(row)
        s.commit()


_SUM_SYS = (
    "You maintain a short running summary of a conversation so an assistant keeps "
    "context once older turns scroll out of view. Merge the PREVIOUS SUMMARY with the "
    "NEW MESSAGES into <=150 words: keep decisions made, facts established, what was "
    "built/produced, and any open threads. Output ONLY the summary text — no preamble."
)


def update_summary(session_id: str, older_messages: list, budget=None) -> None:
    """Fold the messages that scrolled out of the verbatim window into the rolling
    summary. One cheap tier1 call; never raises (memory must not break a turn)."""
    if not older_messages:
        return
    try:
        from core.llm import complete
        from core.registry import registry
        prev = get_summary(session_id)
        convo = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in older_messages)
        model = registry.model_for_tier("tier1")
        resp, _ = complete(
            model,
            [{"role": "system", "content": _SUM_SYS},
             {"role": "user", "content": f"PREVIOUS SUMMARY:\n{prev or '(none)'}\n\nNEW MESSAGES:\n{convo}"}],
            max_tokens=300, budget=budget, temperature=0.2,
        )
        text = (resp.choices[0].message.content or "").strip()
        if text:
            set_summary(session_id, text)
    except Exception as e:
        log.debug("summary update skipped: %s", e)


# ===========================================================================
#  SEMANTIC MEMORY — durable facts about the user / a project ("profile").
# ===========================================================================
def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")[:60] or "fact"


def upsert_fact(text: str, fact_key: str, scope: str = "global") -> None:
    """Insert or replace a fact (deduped by scope+key, so it never piles up)."""
    key = _slug(fact_key)
    with DBSession(engine) as s:
        row = s.exec(
            select(Memory).where(Memory.kind == "fact", Memory.scope == scope,
                                 Memory.fact_key == key)
        ).first()
        if row:
            row.text, row.updated_at = text[:500], _now()
        else:
            row = Memory(kind="fact", scope=scope, fact_key=key, text=text[:500],
                         updated_at=_now())
        s.add(row)
        s.commit()


def get_facts(scopes: list) -> list:
    """Fact texts for the given scopes (e.g. ['global', 'project:<id>']), newest first."""
    if not scopes:
        return []
    # Filter scope in SQL (uses the scope index) instead of scanning every fact and
    # filtering in Python — this runs on every substantive turn.
    with DBSession(engine) as s:
        rows = s.exec(
            select(Memory).where(Memory.kind == "fact", Memory.scope.in_(list(scopes)))
            .order_by(Memory.updated_at.desc())
        ).all()
    return [r.text for r in rows]


def list_facts(scope: str = None) -> list:
    """Full fact records for the Memory UI (view/edit/forget)."""
    with DBSession(engine) as s:
        rows = s.exec(
            select(Memory).where(Memory.kind == "fact").order_by(Memory.updated_at.desc())
        ).all()
    return [{"id": r.id, "text": r.text, "scope": r.scope, "key": r.fact_key,
             "updated_at": r.updated_at}
            for r in rows if scope is None or r.scope == scope]


def forget_fact(fact_id: str) -> bool:
    with DBSession(engine) as s:
        row = s.get(Memory, fact_id)
        if not row or row.kind != "fact":
            return False
        s.delete(row)
        s.commit()
    try:
        from . import vectorstore
        vectorstore.on_write()
    except Exception:
        pass
    return True


_FACT_SYS = (
    "You extract DURABLE facts about the user or their project from a message — the "
    "kind worth remembering across future conversations (name, role, tech stack, "
    "languages, recurring preferences like answer style, the project they're building). "
    "IGNORE one-off task details, questions, and anything transient. If nothing durable "
    "is present, return an empty list. Output ONLY JSON: "
    '{"facts":[{"key":"language","value":"Python"}]}'
)


def extract_facts(user_text: str, scope: str = "global", budget=None) -> list:
    """Pull durable facts from the user's message via a cheap tier1 call and upsert
    them. Gated by the caller; never raises (best-effort). Returns the keys stored."""
    if not user_text or len(user_text.strip()) < 8:
        return []
    try:
        from core.llm import complete
        from core.registry import registry
        model = registry.model_for_tier("tier1")
        resp, _ = complete(
            model,
            [{"role": "system", "content": _FACT_SYS},
             {"role": "user", "content": user_text[:2000]}],
            max_tokens=300, budget=budget, temperature=0,
        )
        raw = resp.choices[0].message.content or ""
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        stored = []
        for f in (data.get("facts") or [])[:10]:
            k, v = f.get("key"), f.get("value")
            if k and v:
                upsert_fact(f"{k}: {v}", k, scope)
                stored.append(_slug(k))
        return stored
    except Exception as e:
        log.debug("fact extraction skipped: %s", e)
        return []


# ===========================================================================
#  PROCEDURAL MEMORY — reusable rules the agent learns from experience.
#  SAFETY: a proposed rule is NEVER followed until a human approves it. Only
#  kind=="rule" (active, approved) rules are injected into context — and those ARE
#  treated as instructions, which is why approval is mandatory. kind=="rule_proposed"
#  rows sit in the review queue and are never injected.
# ===========================================================================
def add_rule(text: str, scope: str = "global", proposed: bool = False) -> str:
    kind = "rule_proposed" if proposed else "rule"
    key = _slug(text)
    with DBSession(engine) as s:
        # dedupe: same text already present (in either state) -> no duplicate
        existing = s.exec(
            select(Memory).where(Memory.kind.in_(["rule", "rule_proposed"]),
                                 Memory.scope == scope, Memory.fact_key == key)
        ).first()
        if existing:
            return existing.id
        row = Memory(kind=kind, scope=scope, fact_key=key, text=text[:500], updated_at=_now())
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id


def list_rules(status: str = None) -> list:
    """Rules for the UI. status: 'active' | 'proposed' | None (both)."""
    kinds = {"active": ["rule"], "proposed": ["rule_proposed"]}.get(status, ["rule", "rule_proposed"])
    with DBSession(engine) as s:
        rows = s.exec(
            select(Memory).where(Memory.kind.in_(kinds)).order_by(Memory.updated_at.desc())
        ).all()
    return [{"id": r.id, "text": r.text, "scope": r.scope,
             "status": "active" if r.kind == "rule" else "proposed",
             "updated_at": r.updated_at} for r in rows]


def get_active_rules(scopes: list) -> list:
    if not scopes:
        return []
    with DBSession(engine) as s:
        rows = s.exec(
            select(Memory).where(Memory.kind == "rule", Memory.scope.in_(list(scopes)))
            .order_by(Memory.updated_at.desc())
        ).all()
    return [r.text for r in rows]


def approve_rule(rule_id: str) -> bool:
    with DBSession(engine) as s:
        row = s.get(Memory, rule_id)
        if not row or row.kind != "rule_proposed":
            return False
        row.kind, row.updated_at = "rule", _now()   # promote proposed -> active
        s.add(row)
        s.commit()
        return True


def delete_rule(rule_id: str) -> bool:
    """Reject a proposal or remove an active rule."""
    with DBSession(engine) as s:
        row = s.get(Memory, rule_id)
        if not row or row.kind not in ("rule", "rule_proposed"):
            return False
        s.delete(row)
        s.commit()
        return True


_RULE_SYS = (
    "You review a completed task and decide if there is ONE durable, reusable WORKING "
    "RULE worth following on similar future tasks for this user/project — e.g. 'run the "
    "test suite before declaring a coding task done' or 'prefer a single self-contained "
    "HTML file for small UIs'. It must be general (not specific to this one task), "
    "actionable, and safe. If there is no such rule, return an empty list. Output ONLY "
    'JSON: {"rules":["..."]} (at most one rule).'
)


def propose_rule(task: str, result: str, scope: str = "global", budget=None) -> list:
    """Suggest at most one reusable rule from a finished task and store it as PROPOSED
    (pending human approval). Cheap tier1 call; gated by caller; never raises."""
    try:
        from core.llm import complete
        from core.registry import registry
        model = registry.model_for_tier("tier1")
        resp, _ = complete(
            model,
            [{"role": "system", "content": _RULE_SYS},
             {"role": "user", "content": f"TASK:\n{task[:1500]}\n\nRESULT:\n{(result or '')[:1500]}"}],
            max_tokens=200, budget=budget, temperature=0,
        )
        raw = resp.choices[0].message.content or ""
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        added = []
        for rule in (data.get("rules") or [])[:1]:
            if isinstance(rule, str) and len(rule.strip()) > 8:
                add_rule(rule.strip(), scope=scope, proposed=True)
                added.append(rule.strip())
        return added
    except Exception as e:
        log.debug("rule proposal skipped: %s", e)
        return []

"""
rag.py — lightweight retrieval over project knowledge files (C4).

Instead of dumping WHOLE project files into every prompt (wasteful + overflows on a big
FRS), this chunks each doc, embeds the chunks (reusing core.llm.embed via memory._vec),
stores them in the Memory table (kind='doc_chunk'), and fetches only the chunks RELEVANT
to the current request. Degrades to a lexical match when no embedding model is set, and
the caller falls back to whole-file injection when RAG returns nothing.
"""
import json

from sqlmodel import Session as DBSession, select

from .db import engine
from .memory import Memory, _vec, _cos, _embed_model, _tokens, _lex


def enabled() -> bool:
    return bool(_embed_model())


def _chunk(text: str, size: int = 1200, overlap: int = 150) -> list:
    text = text or ""
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += max(1, size - overlap)
    return out


def indexed_sources(scope: str) -> set:
    with DBSession(engine) as s:
        rows = s.exec(select(Memory).where(Memory.kind == "doc_chunk", Memory.scope == scope)).all()
    return {m.fact_key for m in rows}


def index_text(text: str, source: str, scope: str) -> int:
    """Index a document's text as retrievable chunks under a scope (e.g. 'project:<id>').
    Idempotent per (scope, source): re-indexing replaces that source's chunks."""
    if not text or not scope:
        return 0
    with DBSession(engine) as s:
        for m in s.exec(select(Memory).where(
                Memory.kind == "doc_chunk", Memory.scope == scope, Memory.fact_key == source)).all():
            s.delete(m)
        n = 0
        for ch in _chunk(text):
            vec = _vec(ch)
            s.add(Memory(kind="doc_chunk", scope=scope, fact_key=source, text=ch[:2000],
                         embedding=json.dumps(vec) if vec else ""))
            n += 1
        s.commit()
    return n


def ensure_indexed(project_id: str) -> None:
    """Index any of a project's knowledge files that aren't indexed yet (lazy)."""
    if not project_id:
        return
    from . import projects
    scope = f"project:{project_id}"
    have = indexed_sources(scope)
    for name, text in projects.file_texts(project_id).items():
        if name not in have:
            index_text(text, name, scope)


def retrieve(query: str, scope: str, k: int = 5) -> list:
    """Top-k relevant chunks for a query within a scope (embeddings, else lexical)."""
    if not scope:
        return []
    with DBSession(engine) as s:
        rows = s.exec(select(Memory).where(Memory.kind == "doc_chunk", Memory.scope == scope)).all()
    if not rows:
        return []
    if _embed_model():
        qv = _vec(query)
        if qv:
            scored = []
            for m in rows:
                if not m.embedding:
                    continue
                try:
                    scored.append((_cos(qv, json.loads(m.embedding)), m.text))
                except Exception:
                    continue
            scored.sort(key=lambda x: -x[0])
            if scored:
                return [t for _, t in scored[:k]]
    q = set(_tokens(query))
    if not q:
        return []
    scored = [(_lex(q, set(_tokens(m.text))), m.text) for m in rows]
    scored.sort(key=lambda x: -x[0])
    return [t for sc, t in scored[:k] if sc > 0]

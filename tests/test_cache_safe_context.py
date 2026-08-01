"""Cache-safe context ordering: stable blocks first, per-query blocks moved to the tail so
the prefix stays byte-identical across turns (lets DeepSeek's automatic prefix cache hit)."""
from server import chat


def test_query_blocks_move_to_tail(monkeypatch):
    monkeypatch.delenv("AGENT_CACHE_SAFE_CONTEXT", raising=False)
    blocks = ["state", "facts", "rules", "RECALL", "summary", "RAG", "ATT", "history"]
    out = chat._order_blocks(blocks, {3, 5, 6})                 # recall, rag, attachments
    assert out == ["state", "facts", "rules", "summary", "history", "RECALL", "RAG", "ATT"]


def test_stable_prefix_is_identical_across_turns(monkeypatch):
    monkeypatch.delenv("AGENT_CACHE_SAFE_CONTEXT", raising=False)
    turn1 = chat._order_blocks(["state", "facts", "R1", "summary", "hist"], {2})
    turn2 = chat._order_blocks(["state", "facts", "R2", "summary", "hist"], {2})
    # the per-query block differs (R1 vs R2) but the cacheable stable prefix is the same
    assert turn1[:-1] == turn2[:-1] == ["state", "facts", "summary", "hist"]


def test_disabled_keeps_original_order(monkeypatch):
    monkeypatch.setenv("AGENT_CACHE_SAFE_CONTEXT", "0")
    blocks = ["a", "Q", "b"]
    assert chat._order_blocks(blocks, {1}) == ["a", "Q", "b"]


def test_no_content_dropped_or_duplicated(monkeypatch):
    monkeypatch.delenv("AGENT_CACHE_SAFE_CONTEXT", raising=False)
    blocks = ["a", "b", "c", "d", "e"]
    out = chat._order_blocks(blocks, {1, 3})
    assert sorted(out) == sorted(blocks) and len(out) == len(blocks)

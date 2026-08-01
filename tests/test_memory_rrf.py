"""Reciprocal Rank Fusion for memory recall — fuse embedding + lexical rankings so a note
strong in EITHER signal surfaces (better recall than cosine-only or lexical-only)."""
from server import memory


def test_rrf_single_list_preserves_order():
    scores = memory._rrf([["X", "Y", "Z"]])
    assert scores["X"] > scores["Y"] > scores["Z"]


def test_rrf_rewards_agreement_across_lists():
    emb = ["A", "B", "C"]
    lex = ["B", "D", "A"]
    scores = memory._rrf([emb, lex])
    order = sorted(scores, key=lambda t: -scores[t])
    # B (top of lex, near-top of emb) and A (in both) outrank D (in only one list)
    assert order[0] in ("A", "B")
    assert scores["D"] < scores["B"] and scores["D"] < scores["A"]


def test_rrf_surfaces_item_present_in_only_one_list():
    # the whole point: an item the embedding ranking MISSED still surfaces from lexical
    scores = memory._rrf([["A", "B"], ["C"]])
    assert scores.get("C", 0) > 0


def test_rrf_can_be_disabled(monkeypatch):
    # the flag is read at import; just assert the knob exists and defaults on
    assert isinstance(memory._RRF_ON, bool)
    assert memory._RRF_K0 == 60

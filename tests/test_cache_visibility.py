"""Prompt-cache visibility: provider-reported cache reads flow into Budget + metrics.

Cache-hit input is ~50-98% cheaper (DeepSeek: 98% off). We surface REAL provider-
reported reads (usage.prompt_tokens_details.cached_tokens / prompt_cache_hit_tokens /
cache_read_input_tokens) — never inferred — so run summaries can't drift from billing.
"""
from types import SimpleNamespace as NS

from core.llm import Budget, _cached_tokens_of
from core import metrics


def _resp(usage):
    return NS(usage=usage)


def test_openai_normalized_shape():
    # LiteLLM-normalized: usage.prompt_tokens_details.cached_tokens
    u = NS(prompt_tokens=1000, prompt_tokens_details=NS(cached_tokens=900))
    assert _cached_tokens_of(_resp(u)) == 900


def test_deepseek_first_party_shape():
    u = {"prompt_tokens": 1000, "prompt_cache_hit_tokens": 940}
    assert _cached_tokens_of(_resp(u)) == 940


def test_anthropic_shape():
    u = {"prompt_tokens": 500, "cache_read_input_tokens": 450}
    assert _cached_tokens_of(_resp(u)) == 450


def test_no_cache_info_is_zero():
    assert _cached_tokens_of(_resp({"prompt_tokens": 100})) == 0
    assert _cached_tokens_of(_resp(None)) == 0
    assert _cached_tokens_of(NS()) == 0        # no usage attr at all


def test_details_present_but_empty_falls_through():
    # details object exists but has no cached count -> try the flat keys.
    u = {"prompt_tokens_details": {}, "prompt_cache_hit_tokens": 77}
    assert _cached_tokens_of(_resp(u)) == 77


def test_budget_accumulates_cached_tokens():
    b = Budget(max_usd=1.0)
    b.add_cached_tokens(900)
    b.add_cached_tokens(100)
    assert b.cached_tokens == 1000


def test_subbudget_rolls_up_to_parent():
    parent = Budget(max_usd=1.0)
    child = parent.child()
    child.add_cached_tokens(500)
    assert child.cached_tokens == 500
    assert parent.cached_tokens == 500


def test_metrics_cache_hit_rate():
    metrics.reset()
    metrics.record("test/model", 1.0, ok=True, cost=0.0,
                   prompt_tokens=1000, cached_tokens=900)
    metrics.record("test/model", 1.0, ok=True, cost=0.0,
                   prompt_tokens=1000, cached_tokens=100)
    row = [r for r in metrics.summary() if r["model"] == "test/model"][0]
    assert row["cached_tokens"] == 1000
    assert row["cache_hit_rate"] == 0.5
    metrics.reset()


def test_metrics_no_tokens_rate_is_none():
    metrics.reset()
    metrics.record("test/other", 1.0, ok=True, cost=0.0)
    row = [r for r in metrics.summary() if r["model"] == "test/other"][0]
    assert row["cache_hit_rate"] is None
    metrics.reset()

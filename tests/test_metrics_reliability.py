"""metrics.summary() must expose the rolling reliability + `degraded` flag — the signal the
router acts on (registry.ranked_for deprioritizes degraded models) and the Health UI shows —
WITHOUT deadlocking. reliability()/is_degraded() re-acquire the same lock summary() holds, so
they're computed after the lock is released; this guards that ordering.
"""
from core import metrics


def test_summary_carries_reliability_and_degraded():
    metrics.reset()
    try:
        for _ in range(6):
            metrics.record("good/model", 0.1, ok=True)
        metrics.record("bad/model", 0.1, ok=True)
        for _ in range(5):
            metrics.record("bad/model", 0.1, ok=False)

        rows = {r["model"]: r for r in metrics.summary()}   # must return, not deadlock

        assert rows["good/model"]["reliability"] == 1.0
        assert rows["good/model"]["degraded"] is False
        assert rows["bad/model"]["reliability"] < 0.5
        assert rows["bad/model"]["degraded"] is True
    finally:
        metrics.reset()

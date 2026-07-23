"""Cost accounting falls back to the provider's usage.estimated_cost when litellm's price
map has no price for a model (vision VLMs especially) — so vision spend still counts against
the Budget + daily cap (invariant #3). Regression for the "vision logs $0" finding."""
from core import llm


class _Usage:
    def __init__(self, est):
        self.estimated_cost = est


class _Resp:
    def __init__(self, est=None, response_cost=None):
        self.usage = _Usage(est)
        self._hidden_params = {"response_cost": response_cost}


def test_cost_falls_back_to_estimated_cost():
    assert abs(llm._cost_of(_Resp(est=0.00010668)) - 0.00010668) < 1e-9


def test_response_cost_wins_when_present():
    # litellm knows the price → use it, ignore the provider estimate
    assert llm._cost_of(_Resp(est=0.5, response_cost=0.002)) == 0.002


def test_zero_when_no_cost_info():
    class _Bare:
        _hidden_params = {}
        usage = None
    assert llm._cost_of(_Bare()) == 0.0

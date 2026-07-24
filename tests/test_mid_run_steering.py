"""Mid-run steering: the user can add instructions to a LIVE run without interrupting it.
The carrier is the Budget object (the one thread-safe channel shared between the async WS
handler and the run worker thread). A sub-budget (each agent runs under one) must see
injections made into the ROOT run budget."""
from core.llm import Budget


def test_inject_and_drain():
    b = Budget()
    assert b.drain_injections() == []          # empty to start
    b.inject("also add a due-date field")
    b.inject("   ")                              # blank ignored
    b.inject("and a search box")
    drained = b.drain_injections()
    assert drained == ["also add a due-date field", "and a search box"]
    assert b.drain_injections() == []          # drain is one-shot


def test_subbudget_delegates_to_root():
    root = Budget()
    child = root.child()                         # what an agent actually runs under
    root.inject("new instruction mid-run")
    # the agent loop drains its (child) budget and must still see the root injection
    assert child.drain_injections() == ["new instruction mid-run"]
    assert root.drain_injections() == []         # already drained via the child->parent path


def test_child_inject_reaches_root():
    root = Budget()
    child = root.child()
    child.inject("from the child")
    assert root.drain_injections() == ["from the child"]

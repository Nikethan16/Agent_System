"""Tests for per-project spend tracking + budget cap (server/spend.py, projects.py)."""
import pytest

from server import db, spend, projects

db.init_db()


def test_record_and_sum_by_project():
    p = projects.create("budget-test")
    pid = p["id"]
    assert spend.spent_by_project(pid) == 0.0
    spend.record(0.10, project_id=pid)
    spend.record(0.05, project_id=pid)
    spend.record(0.99, project_id="some-other-project")
    assert abs(spend.spent_by_project(pid) - 0.15) < 1e-9


def test_budget_cap_set_and_enforced():
    p = projects.create("capped")
    pid = p["id"]
    projects.update(pid, budget_usd=0.20)
    assert projects.budget_of(pid) == 0.20
    spend.record(0.15, project_id=pid)
    assert not spend.project_over_cap(pid, projects.budget_of(pid))
    spend.record(0.10, project_id=pid)   # now 0.25 >= 0.20
    assert spend.project_over_cap(pid, projects.budget_of(pid))


def test_zero_budget_is_unlimited():
    p = projects.create("uncapped")
    pid = p["id"]
    spend.record(99.0, project_id=pid)
    assert projects.budget_of(pid) == 0.0
    assert not spend.project_over_cap(pid, 0.0)


def test_project_status_shape():
    p = projects.create("status")
    pid = p["id"]
    projects.update(pid, budget_usd=1.0)
    spend.record(0.25, project_id=pid)
    st = spend.project_status(pid, projects.budget_of(pid))
    assert st["spent"] == 0.25 and st["cap"] == 1.0 and st["remaining"] == 0.75

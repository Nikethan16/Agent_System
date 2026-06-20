"""Tests for the spend time-series / overview analytics (server/spend.py)."""
from server import db, spend, projects

db.init_db()


def test_history_is_continuous_series():
    h = spend.history(days=7)
    assert len(h) == 7
    # oldest first, each entry has day + usd, days are distinct and ascending
    days = [e["day"] for e in h]
    assert days == sorted(days)
    assert all("usd" in e for e in h)


def test_history_reflects_recorded_spend():
    spend.record(0.07)   # today, no project
    h = spend.history(days=3)
    assert h[-1]["usd"] >= 0.07   # today's bucket is the last entry


def test_overview_shape():
    p = projects.create("overview-proj")
    spend.record(0.40, project_id=p["id"])
    projects.update(p["id"], budget_usd=2.0)
    ov = spend.overview()
    assert "spent_today" in ov and "all_time" in ov and "history" in ov
    assert isinstance(ov["history"], list)
    assert ov["all_time"] >= 0.40


def test_by_project_excludes_standalone():
    p = projects.create("only-this")
    spend.record(0.11, project_id=p["id"])
    spend.record(0.22, project_id="")   # standalone chat
    bp = spend.by_project_all()
    assert bp.get(p["id"], 0) >= 0.11
    assert "" not in bp

"""Difficulty routing (regression for the deep-test finding that the multi-tenant Kanban build
scored only ~3 on the old heuristic — below the >=5 bump — so it stayed tier-2 on the flash
model and never reached the strong-model phased-build path).

The strengthened _difficulty_score must recognise real hard-architecture signals (REST endpoint
lines, multi-tenant, RBAC, auth, DB, backend) so a genuine full app escalates, while trivial and
medium tasks stay low (no cost over-escalation)."""
from core.orchestrator import _difficulty_score

HARD_KANBAN = """Build a MULTI-TENANT Kanban board web app from scratch. Backend: a FastAPI app
in app.py persisting to SQLite. Endpoints:
  POST /users {username} -> {id}
  POST /boards {owner_id, title} -> {id}
  GET  /boards/{board_id}?user_id=..  -> 403 unless owner or member
  POST /boards/{board_id}/members {owner_id, member_id, role}
  POST /cards/{card_id}/move {user_id, to_column, to_index}
  DELETE /boards/{board_id} {user_id}
Rules: tenant ISOLATION, RBAC role-based access, authentication/login. Write a pytest suite."""


def test_hard_multitenant_build_escalates():
    # must clear the >=5 bump threshold so it routes to tier-3 (strong model)
    assert _difficulty_score(HARD_KANBAN) >= 5


def test_trivial_tasks_do_not_escalate():
    assert _difficulty_score("Create fizzbuzz.py with tests and run them.") < 5
    assert _difficulty_score("Run pytest. Two tests fail. Fix the bugs in expenses.py.") < 5
    assert _difficulty_score("what does the SQL LEFT JOIN do?") < 5


def test_endpoint_contract_is_a_strong_signal():
    # a short spec that is nonetheless a real REST API should register complexity
    api = ("Build an API:\n  POST /login\n  GET /items\n  POST /items\n  DELETE /items/{id}\n"
           "with auth and a sqlite database.")
    assert _difficulty_score(api) >= 5

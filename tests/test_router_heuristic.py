"""The keyword heuristic fallback (used when the LLM classifier errors) must match the USER'S
request, not the injected project context, and must route a plain QUESTION to answer-mode.
Regression: 'how do I deploy this app' fell to the heuristic, matched tech words in the injected
context, routed to 'coding' -> tier 3 -> 45 wasted rounds."""
from core import router as r


def _route(user_req: str, context: str = "") -> dict:
    # Mirror the assembled-task shape: context preamble + the 'NEW REQUEST:' marker + the ask.
    task = f"{context}\n\nNEW REQUEST:{user_req}" if context else user_req
    return r._heuristic_route(task, Exception("APIError"))


def test_deploy_question_with_techy_context_routes_to_answer_not_build():
    ctx = "Project context: a FastAPI + Python app using pytest, SQL, an api with endpoints."
    out = _route("How do I deploy this application to production?", ctx)
    assert out["task_type"] in ("general", "research")   # NOT 'coding'
    assert out["tier"] == 2


def test_plain_what_question_is_general():
    assert _route("what is the difference between tier 2 and tier 3?")["task_type"] == "general"


def test_why_question_is_general():
    assert _route("why does the classifier sometimes pick tier 3?")["task_type"] == "general"


def test_research_question_routes_research():
    assert _route("what are the latest news on open-source AI models online?")["task_type"] == "research"


def test_build_request_still_codes():
    assert _route("build a REST API endpoint with pytest tests")["task_type"] == "coding"


def test_command_with_build_verb_stays_build():
    # "fix the bug" is a command, not a how-to question.
    assert _route("fix the bug in the login endpoint")["task_type"] == "coding"


def test_greeting_is_tier1_chat():
    out = _route("hi")
    assert out["tier"] == 1 and out["task_type"] == "chat"

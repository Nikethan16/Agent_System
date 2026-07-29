"""A how-to / "what do I do now" QUESTION must route to answer-mode, never the build path.
Regression for a live failure where "how do I deploy this app" was tagged coding -> tier 3 ->
architect+coder, spun 45 rounds, and returned a bare "(stopped: iteration cap hit)"."""
from core import orchestrator as o


def test_deploy_question_is_instructional():
    assert o._instructional_question("How do I deploy this application to production?")
    assert o._instructional_question("what are the steps to set up the backend?")
    assert o._instructional_question("walk me through hosting the frontend")
    assert o._instructional_question("give me step-by-step instructions for the database")
    assert o._instructional_question("help me configure Redis")
    assert o._instructional_question("what do I do now?")
    assert o._instructional_question("how to run the worker locally")


def test_build_requests_are_not_instructional():
    # A leading build verb means DO it, not explain it — must stay on the build path.
    assert not o._instructional_question("build a deploy script for the backend")
    assert not o._instructional_question("write the Dockerfile and CI config")
    assert not o._instructional_question("implement the deploy endpoint")
    assert not o._instructional_question("create a setup guide page component")
    # A plain build/feature request is not a how-to.
    assert not o._instructional_question("add a points_to_next_tier helper to confidence.py")


def test_plain_statements_are_not_instructional():
    assert not o._instructional_question("The capital of France is Paris.")
    assert not o._instructional_question("summarize what this repo does")  # RU verb, not how-to
    assert not o._instructional_question("")


# ---- failure safety net: a failed run must give next-steps, never a bare marker ----

class _B:
    spent_usd = 0.01


def test_failure_guidance_adds_next_steps_on_cap():
    out = o._failure_guidance("(stopped: iteration cap hit: 45)")
    assert "(stopped: iteration cap hit: 45)" in out          # keeps the honest reason
    assert "continue" in out.lower() and "what do i do now" in out.lower()  # + concrete next steps


def test_failure_guidance_provider_error():
    assert "try again" in o._failure_guidance("(provider error: APIError)").lower()


def test_failure_guidance_empty_response():
    assert "try again" in o._failure_guidance("(the model returned an empty response)").lower()


def test_failure_guidance_noop_on_normal_answer():
    ans = "Here are the deploy steps:\n1. Provision Postgres\n2. Set env vars"
    assert o._failure_guidance(ans) == ans                    # a real answer is untouched


def test_final_payload_wraps_failure_but_not_success():
    fail = o._final_payload("(stopped: iteration cap hit: 30)", _B())
    assert fail["type"] == "final" and "continue" in fail["text"].lower()
    ok = o._final_payload("The answer is 42.", _B())
    assert ok["text"] == "The answer is 42."

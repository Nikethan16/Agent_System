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

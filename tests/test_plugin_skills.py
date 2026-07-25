"""The skills borrowed from the Claude Code plugin evaluation (2026-07-25):
security-guidance (advisory secure-coding), code-review (high-signal rubric),
verification-before-completion (prove-before-done), and the aesthetic method folded
into web-frontend. These are markdown SKILL.md drop-ins — this test guards that they
load, parse, select on the right tasks, and scan clean (so they stay enabled)."""
from types import SimpleNamespace

from core import skills as sk

NEW = ["security-guidance", "code-review", "verification-before-completion"]


def test_new_skills_load_and_parse():
    sk.load()
    names = {s.name for s in sk._SKILLS}
    for n in NEW:
        assert n in names, f"{n} did not load"
        s = sk.get(n)
        assert s.description and s.body, f"{n} missing description/body"


def test_security_guidance_selects_on_risky_code_task():
    picked = [s.name for s in sk.select("build a login endpoint that runs a SQL query on user input")]
    assert "security-guidance" in picked


def test_code_review_selects_on_review_task():
    picked = [s.name for s in sk.select("review this pull request for bugs")]
    assert "code-review" in picked


def test_verification_selects_on_completion_task():
    picked = [s.name for s in sk.select("finish the app and confirm every feature works before marking done")]
    assert "verification-before-completion" in picked


def test_web_frontend_carries_design_guidance():
    s = sk.get("web-frontend")
    assert "design" in s.keywords          # aesthetic method folded in
    assert "signature element" in s.body.lower()


def test_code_review_restricted_to_reviewer_agents():
    # The agents: allowlist must gate auto-matching: a plain coder shouldn't pull the
    # reviewer rubric, but the code-reviewer agent should.
    coder = SimpleNamespace(id="coder", capabilities=[], tools=[])
    reviewer = SimpleNamespace(id="code-reviewer", capabilities=[], tools=[])
    task = "review this diff and report findings"
    assert "code-review" not in [s.name for s in sk.select(task, agent=coder)]
    assert "code-review" in [s.name for s in sk.select(task, agent=reviewer)]


def test_new_skills_not_blocked_by_scanner():
    # A skill body is injected as agent guidance; these must not be scanned 'risky' (which
    # hard-blocks enabling). The secure-coding / review skills legitimately NAME dangerous
    # patterns to warn against them, so 'caution' is expected and fine; 'risky' would be a
    # false positive that locks a reviewed, bundled skill out.
    for n in NEW:
        assert sk.scan(n).get("risk") != "risky", f"{n} wrongly hard-blocked by skill_scan"

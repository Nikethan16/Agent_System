"""Startup env-var hygiene checks — catch placeholder / quoted / CR-tainted / whitespace-padded
credential values (the silent config incidents from HANDOFF). Never leaks secret values."""
import logging

from server import envcheck


def test_placeholder_value_flagged():
    issues = envcheck.env_hygiene({"GITHUB_TOKEN": "ghp_your_token_here"})
    assert any(i["var"] == "GITHUB_TOKEN" and "placeholder" in i["issue"] for i in issues)


def test_quoted_value_flagged():
    issues = envcheck.env_hygiene({"DEEPSEEK_API_KEY": '"sk-realkey1234567890"'})
    assert any(i["issue"] == "is wrapped in quotes" for i in issues)


def test_cr_character_flagged():
    issues = envcheck.env_hygiene({"GROQ_API_KEY": "gsk_abc123def456ghi789\r"})
    assert any("CR" in i["issue"] for i in issues)


def test_whitespace_flagged():
    issues = envcheck.env_hygiene({"GEMINI_API_KEY": "AIzaRealLookingKey12345  "})
    assert any("whitespace" in i["issue"] for i in issues)


def test_clean_value_no_issue():
    assert envcheck.env_hygiene({"GEMINI_API_KEY": "AIzaSyRealLookingKey1234567890abcdef"}) == []


def test_unset_or_empty_not_flagged():
    assert envcheck.env_hygiene({}) == []
    assert envcheck.env_hygiene({"GITHUB_TOKEN": ""}) == []


def test_realistic_random_token_no_false_positive():
    assert envcheck.env_hygiene({"DEEPINFRA_API_KEY": "abcDEF123456ghiJKL789mnoPQRstu"}) == []


def test_output_never_contains_the_secret_value():
    issues = envcheck.env_hygiene({"GITHUB_TOKEN": "ghp_your_token_here"})
    for i in issues:
        assert set(i.keys()) == {"var", "issue", "hint"}
        assert "ghp_your_token_here" not in str(i)


def test_warn_logs_and_returns(caplog):
    with caplog.at_level(logging.WARNING):
        issues = envcheck.warn_env_hygiene({"GITHUB_TOKEN": "changeme"})
    assert issues and any("ENV HYGIENE" in r.message for r in caplog.records)

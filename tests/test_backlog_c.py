"""Tests for the backlog-C items: generate_image pooled key (C2) + weak-login warning (C6)."""
from core import llm
from server import auth


# ---- C2: generate_image passes a pooled api_key --------------------------
def test_generate_image_passes_api_key(monkeypatch):
    captured = {}

    class _R:
        data = [{"url": "x"}]
        _hidden_params = {}

    def fake_img(**kwargs):
        captured.update(kwargs)
        return _R()

    monkeypatch.setattr(llm.litellm, "image_generation", fake_img)
    llm.generate_image("a cat", "gemini/some-image-model")
    assert "api_key" in captured          # key is now passed (was env-only before)
    assert captured["model"] == "gemini/some-image-model"


# ---- C6: weak login-password warning -------------------------------------
def test_weak_login_flagged(monkeypatch):
    monkeypatch.setenv("AGENT_LOGIN_EMAIL", "me@example.com")
    monkeypatch.setenv("AGENT_LOGIN_PASSWORD", "admin")        # short + common
    issues = auth.warn_if_weak_login()
    assert issues                                              # flagged


def test_strong_login_not_flagged(monkeypatch):
    monkeypatch.setenv("AGENT_LOGIN_EMAIL", "me@example.com")
    monkeypatch.setenv("AGENT_LOGIN_PASSWORD", "Tר9_kx2-Lm84qZ!vbN0")   # long, mixed
    assert auth.warn_if_weak_login() == []


def test_no_login_configured_no_warning(monkeypatch):
    monkeypatch.delenv("AGENT_LOGIN_EMAIL", raising=False)
    monkeypatch.delenv("AGENT_LOGIN_PASSWORD", raising=False)
    assert auth.warn_if_weak_login() == []

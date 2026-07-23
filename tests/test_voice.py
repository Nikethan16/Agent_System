"""Speech-to-text model resolver: STT_MODEL wins, else pick by available provider key
(Groq's free Whisper preferred), else none (mic button hidden)."""
from server.api import voice

_KEYS = ("STT_MODEL", "GROQ_API_KEY", "DEEPINFRA_API_KEY", "OPENAI_API_KEY")


def _clear(monkeypatch):
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)


def test_env_override_wins(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("STT_MODEL", "groq/whisper-large-v3-turbo")
    assert voice.stt_model() == "groq/whisper-large-v3-turbo"


def test_prefers_groq_then_deepinfra(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DEEPINFRA_API_KEY", "y")
    assert voice.stt_model() == "deepinfra/openai/whisper-large-v3"
    monkeypatch.setenv("GROQ_API_KEY", "x")
    assert voice.stt_model() == "groq/whisper-large-v3"      # Groq preferred when both present


def test_none_when_no_key(monkeypatch):
    _clear(monkeypatch)
    assert voice.stt_model() == ""

"""Auto-titling an untitled chat from its first user message (server/db.py)."""
from server import db

db.init_db()


def test_first_user_message_titles_the_chat():
    s = db.create_session()                       # default title "New chat"
    db.add_message(s.id, "user", "How do I deploy the app to the VM?")
    assert db.get_session(s.id)["title"] == "How do I deploy the app to the VM?"


def test_long_message_is_truncated():
    s = db.create_session()
    long = "Please refactor the entire orchestration layer and also rewrite the router"
    db.add_message(s.id, "user", long)
    title = db.get_session(s.id)["title"]
    assert title.endswith("…") and len(title) <= 49


def test_second_message_does_not_retitle():
    s = db.create_session()
    db.add_message(s.id, "user", "first question here")
    db.add_message(s.id, "user", "a totally different follow-up")
    assert db.get_session(s.id)["title"] == "first question here"


def test_assistant_message_never_titles():
    s = db.create_session()
    db.add_message(s.id, "assistant", "some answer")
    assert db.get_session(s.id)["title"] == "New chat"


def test_manual_title_is_not_clobbered():
    s = db.create_session(title="My named chat")
    db.add_message(s.id, "user", "hello there")
    assert db.get_session(s.id)["title"] == "My named chat"


def test_whitespace_only_leaves_default():
    s = db.create_session()
    db.add_message(s.id, "user", "   \n  ")
    assert db.get_session(s.id)["title"] == "New chat"

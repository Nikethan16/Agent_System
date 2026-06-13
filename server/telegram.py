"""
telegram.py — control the agent from your phone via a Telegram bot.

A long-polling bot (getUpdates) so it works from localhost with NO public URL/webhook.
Each Telegram chat maps to a persistent session, so memory + project state carry over
between messages just like the web UI. Runs unattended (auto-approve path, same as the
job queue; policy hard-blocks still apply — there's no Approve button in chat yet).

PLACEHOLDERS you provide (in .env) — the bot is a NO-OP until the token is set:
  TELEGRAM_BOT_TOKEN          from @BotFather (https://t.me/BotFather → /newbot)
  TELEGRAM_ALLOWED_CHAT_IDS   comma-separated chat ids allowed to use it (fail-closed:
                              if unset, the bot replies with YOUR chat id and refuses
                              to run anything until you allowlist it)
  TELEGRAM_MAX_USD            per-message budget cap (default 0.5)

Uses httpx (already a dependency). No new packages.
"""
import os
import time
import logging
import threading

import httpx

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"
_started = False
_lock = threading.Lock()
_MAP = {}   # telegram chat_id -> session_id (in-memory; falls back to DB lookup by title)


def _token() -> str:
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def _allowed() -> set:
    raw = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "")
    return {x.strip() for x in raw.split(",") if x.strip()}


def _call(method: str, **params):
    r = httpx.post(_API.format(token=_token(), method=method), json=params, timeout=60)
    r.raise_for_status()
    return r.json()


def _send(chat_id, text: str):
    text = text or "(no output)"
    for i in range(0, len(text), 3900):          # Telegram caps messages at 4096 chars
        try:
            _call("sendMessage", chat_id=chat_id, text=text[i:i + 3900])
        except Exception as e:
            log.warning("telegram send failed: %s", e)


def _session_for(chat_id: str) -> str:
    """Find-or-create this chat's persistent session (titled 'Telegram <id>'), so the
    conversation persists across messages and restarts."""
    from . import db
    sid = _MAP.get(chat_id)
    if sid and db.get_session(sid):
        return sid
    title = f"Telegram {chat_id}"
    for s in db.list_sessions():
        if s.get("title") == title:
            _MAP[chat_id] = s["id"]
            return s["id"]
    sid = db.create_session(title=title).id
    _MAP[chat_id] = sid
    return sid


def _handle(update: dict):
    from . import chat, db
    from core.llm import Budget
    msg = update.get("message") or update.get("edited_message") or {}
    chat_id = str((msg.get("chat") or {}).get("id") or "")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return

    allowed = _allowed()
    if not allowed:                               # fail-closed: tell the user how to enable
        _send(chat_id, f"This bot isn't allowlisted yet. Add this to .env and restart:\n"
                       f"TELEGRAM_ALLOWED_CHAT_IDS={chat_id}")
        return
    if chat_id not in allowed:
        _send(chat_id, "⛔ This bot is private — your chat id isn't allowed.")
        return

    if text in ("/start", "/help"):
        _send(chat_id, "AGENT // CORE bot. Send me a task and I'll run it (research, code, "
                       "documents…). /new starts a fresh chat.")
        return
    if text == "/new":
        _MAP[chat_id] = db.create_session(title=f"Telegram {chat_id}").id
        _send(chat_id, "Started a fresh chat. ✨")
        return

    sid = _session_for(chat_id)
    _send(chat_id, "🤖 on it…")
    try:
        budget = Budget(max_usd=float(os.environ.get("TELEGRAM_MAX_USD", "0.5")),
                        max_iterations=30)
        final = chat.run_turn(sid, text, budget=budget)
        _send(chat_id, final or "(done)")
    except Exception as e:
        _send(chat_id, f"⚠️ error: {type(e).__name__}: {e}")


def maybe_notify(session_id: str, text: str) -> bool:
    """If `session_id` is a Telegram-linked chat, push `text` to it (best-effort).
    This is what makes a SCHEDULED task ('every morning, research X') deliver its result
    to your phone: the job runs in a 'Telegram <chat_id>' session, then this pushes it."""
    if not _token() or not text:
        return False
    from . import db
    title = (db.get_session(session_id) or {}).get("title") or ""
    if not title.startswith("Telegram "):
        return False
    chat_id = title.split(" ", 1)[1].strip()
    allowed = _allowed()
    if chat_id and (not allowed or chat_id in allowed):
        _send(chat_id, text)
        return True
    return False


def _loop():
    log.info("Telegram bot started (long-polling).")
    offset = 0
    while True:
        try:
            resp = _call("getUpdates", offset=offset, timeout=30)
            for u in resp.get("result", []):
                offset = u["update_id"] + 1
                try:
                    _handle(u)
                except Exception as e:
                    log.warning("telegram handle failed: %s", e)
        except Exception as e:
            log.warning("telegram poll failed: %s", e)
            time.sleep(5)


def start_telegram():
    """Idempotent: start the bot IF a token is configured; otherwise a logged no-op."""
    global _started
    if not _token():
        log.info("Telegram disabled (set TELEGRAM_BOT_TOKEN to enable mobile control).")
        return False
    with _lock:
        if _started:
            return True
        _started = True
    threading.Thread(target=_loop, daemon=True).start()
    return True

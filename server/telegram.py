"""
telegram.py — control the agent from your phone via a Telegram bot.

A long-polling bot (getUpdates) so it works from localhost with NO public URL/webhook.
Each Telegram chat maps to a persistent session, so memory + project state carry over
between messages just like the web UI. Each task runs in its own thread (so the poll loop
stays responsive); risky actions that need a human are sent to the chat and you answer
with `/yes <id>` or `/no <id>` — the same approval that the web UI raises, now answerable
from your phone. Policy hard-blocks still apply.

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
                       "documents…). /new starts a fresh chat. When I need permission for a "
                       "risky action I'll ask — reply /yes <id> or /no <id>.")
        return
    if text == "/new":
        _MAP[chat_id] = db.create_session(title=f"Telegram {chat_id}").id
        _send(chat_id, "Started a fresh chat. ✨")
        return

    # Answer a pending approval from the phone: "/yes <id>" or "/no <id>".
    low = text.lower()
    if low.startswith(("/yes", "/no", "/approve", "/deny")):
        from . import approvals
        parts = text.split()
        req_id = parts[1] if len(parts) > 1 else ""
        allow = low.startswith(("/yes", "/approve"))
        ok = bool(req_id) and approvals.resolve(req_id, allow, "via telegram", decided_by="telegram")
        if not ok:           # no live waiter — still record the verdict if the row exists
            from . import runs
            ok = runs.resolve_approval(req_id, "approved" if allow else "denied", "telegram")
        _send(chat_id, ("✅ approved" if allow else "🚫 denied") if ok
                       else "Couldn't find that pending approval — check the id.")
        return

    sid = _session_for(chat_id)
    _send(chat_id, "🤖 on it…")
    _run_task_async(chat_id, sid, text)


def _run_task_async(chat_id: str, sid: str, text: str):
    """Run one task in its OWN thread so the long-poll loop stays free to receive the
    user's /yes /no approval replies while the task waits on them."""
    from . import chat, runs, approvals
    from core.llm import Budget

    def _emit(ev):
        # Only surface approval prompts to the chat (other events would be noise); the
        # user answers with /yes <id> or /no <id>, which approvals.resolve() routes back.
        if isinstance(ev, dict) and ev.get("type") == "approval_request":
            _send(chat_id, f"⚠️ Approval needed: tool {ev.get('tool')} (risk={ev.get('risk')}).\n"
                           f"{ev.get('reason', '')}\nReply /yes {ev.get('id')} to approve, "
                           f"or /no {ev.get('id')} to deny.")

    def _worker():
        budget = Budget(max_usd=float(os.environ.get("TELEGRAM_MAX_USD", "0.5")),
                        max_iterations=30)
        run_id = runs.start_run(sid, text)
        broker = approvals.ApprovalBroker(_emit, budget=budget, mode="auto",
                                          task_context=text, session_id=sid, run_id=run_id)
        status = "done"
        try:
            final = chat.run_turn(sid, text, budget=budget, approve=broker.approve)
            _send(chat_id, final or "(done)")
        except Exception as e:
            status = "error"
            _send(chat_id, f"⚠️ error: {type(e).__name__}: {e}")
        finally:
            runs.finish_run(run_id, status, budget.spent_usd)

    threading.Thread(target=_worker, daemon=True).start()


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

"""
envcheck.py — startup hygiene checks for credential / config env vars.

Catches the SILENT config incidents from HANDOFF: a `ghp_your_token_here` placeholder that
OVERRODE the real GITHUB_TOKEN, and a token pasted on Windows that carried a stray quote + CR
line-ending. In all of these the app "has" the variable — it's just wrong — so nothing fails
loudly. This scans the important vars at startup, logs a clear warning per problem, and exposes
the same list via /api/system/env-hygiene for a future Settings card. Never raises; never logs
or returns a secret VALUE (only the variable name + the kind of problem).
"""
import os
import logging

log = logging.getLogger(__name__)

# Vars worth checking WHEN SET — credentials + auth/config that has actually bitten us. A var
# that is simply unset is NOT flagged (it's just unconfigured, which is fine).
_CHECKED = [
    "GITHUB_TOKEN", "AGENT_AUTH_TOKEN", "AGENT_LOGIN_PASSWORD",
    "DEEPSEEK_API_KEY", "DEEPINFRA_API_KEY", "GEMINI_API_KEY", "NVIDIA_NIM_API_KEY",
    "GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY", "SEARCH_API_KEY", "MISTRAL_API_KEY", "SAMBANOVA_API_KEY",
    "TOGETHER_API_KEY", "EMBED_MODEL",
]

# Substrings that only ever appear in leftover TEMPLATE values, never in a real secret.
_PLACEHOLDER_MARKERS = (
    "your_token", "your-token", "yourtoken", "your_key", "your-key", "yourkey",
    "changeme", "change_me", "placeholder", "replace_me", "replace-this", "replaceme",
    "xxxx", "<your", "here>", "sk-your", "ghp_your", "example_key", "todo:", "...",
)


def env_hygiene(env=None):
    """Return [{var, issue, hint}] for hygiene problems in SET vars. Secret values never leave
    this function — only the variable name and the problem kind."""
    env = os.environ if env is None else env
    issues = []
    for var in _CHECKED:
        raw = env.get(var)
        if not raw:                       # unset or empty -> not a problem
            continue
        low = raw.lower()
        if any(mark in low for mark in _PLACEHOLDER_MARKERS):
            issues.append({"var": var, "issue": "looks like a leftover placeholder value",
                           "hint": "replace it with the real value — a template value silently "
                                   "overrides the real one"})
            continue                      # a placeholder dwarfs the finer checks
        if "\r" in raw or "\n" in raw:
            issues.append({"var": var, "issue": "contains a CR/newline character",
                           "hint": "re-paste on a single line (a Windows paste can carry a stray CR)"})
        if len(raw) >= 2 and raw[0] in "'\"" and raw[-1] == raw[0]:
            issues.append({"var": var, "issue": "is wrapped in quotes",
                           "hint": "remove the surrounding quotes — in a .env file they become "
                                   "part of the value"})
        if raw != raw.strip():
            issues.append({"var": var, "issue": "has leading/trailing whitespace",
                           "hint": "trim it — surrounding spaces are part of the value"})
    return issues


def warn_env_hygiene(env=None):
    """Log a warning per hygiene issue at startup. Returns the list (for tests / the API)."""
    issues = env_hygiene(env)
    for it in issues:
        log.warning("ENV HYGIENE: %s %s — %s", it["var"], it["issue"], it["hint"])
    return issues

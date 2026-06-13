"""
keypool.py — provider-agnostic API-key pooling with least-loaded scheduling.

WHY: free tiers rate-limit per key (e.g. NVIDIA NIM ~40 RPM). With several keys
for the same provider, we can run faster by spreading calls across them. This is
NOT naive round-robin: each call picks the key with the MOST remaining headroom
in the current rolling window, paces to stay under the limit, and benches a key
that has errored (cooldown) — so the whole pool is optimized as one bucket.

Stays in `core/` and uses only the standard library (no provider SDK, no web, no
model names) — it just hands `complete()` an api_key string to use for one call.

Keys are discovered from the environment: for a provider whose base var is e.g.
NVIDIA_NIM_API_KEY, we also pick up NVIDIA_NIM_API_KEY_1, _2, … _20. Add another
free account's key as NVIDIA_NIM_API_KEY_2 and throughput scales automatically.
"""
import os
import json
import time
import threading
from collections import deque

# provider (the prefix LiteLLM resolves) -> the base env var holding its key.
_PROVIDER_ENV = {
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

# Default per-key requests-per-minute ceiling and the rolling window (seconds).
_DEFAULT_RPM = int(os.environ.get("AGENT_KEY_RPM", "40"))
_WINDOW = 60.0
# How long a key sits out after a rate-limit / error before it's tried again.
_COOLDOWN = float(os.environ.get("AGENT_KEY_COOLDOWN", "20"))
# Max seconds acquire() will pace-wait before using the least-loaded key anyway.
_MAX_WAIT = float(os.environ.get("AGENT_KEY_MAX_WAIT", "8"))


def provider_of(model: str) -> str:
    """The provider prefix for a LiteLLM model string ('' if none/local)."""
    if not model:
        return ""
    if "/" in model:
        return model.split("/", 1)[0]
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    return ""


def mask(key: str) -> str:
    """A safe, non-secret label for a key (for the UI / logs)."""
    if not key:
        return "(none)"
    return f"{key[:4]}…{key[-4:]}" if len(key) > 9 else "****"


# UI-managed keys live in a gitignored JSON store (provider -> [keys]); they're
# pooled ALONGSIDE the env keys, so you can add another free account's key from the
# Settings UI without editing .env. core stays server-agnostic — the path is derived
# from DATA_DIR (same default as server/db.py) via the env, with no server import.
_STORE = os.path.join(
    os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")),
    "keys.json",
)


def _load_store() -> dict:
    try:
        with open(_STORE, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_store(d: dict) -> None:
    os.makedirs(os.path.dirname(_STORE), exist_ok=True)
    with open(_STORE, "w", encoding="utf-8") as f:
        json.dump(d, f)


def _discover_keys(base_env: str, provider: str = "") -> list:
    """Collect keys for a provider: env BASE, BASE_1 … BASE_20, PLUS any UI-added keys
    in the store (deduped). Values <=5 chars are treated as unset placeholders (the repo
    uses 1-char placeholders for unused providers)."""
    out, seen = [], set()
    for name in [base_env] + [f"{base_env}_{i}" for i in range(1, 21)]:
        v = (os.environ.get(name) or "").strip().strip('"').strip("'")
        if len(v) > 5 and v not in seen:
            seen.add(v)
            out.append(v)
    for v in (_load_store().get(provider) or []):
        v = (v or "").strip()
        if len(v) > 5 and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def add_key(provider: str, key: str) -> None:
    """Add a UI-managed key for a provider and rebuild the pool to pick it up."""
    if provider not in _PROVIDER_ENV:
        raise ValueError(f"unknown provider: {provider}")
    key = (key or "").strip()
    if len(key) <= 5:
        raise ValueError("key too short")
    d = _load_store()
    lst = d.get(provider) or []
    if key not in lst:
        lst.append(key)
    d[provider] = lst
    _save_store(d)
    rebuild_pools()


def remove_key(provider: str, masked: str) -> bool:
    """Remove a UI-managed key by its masked label (env keys are not removable here)."""
    d = _load_store()
    lst = d.get(provider) or []
    kept = [k for k in lst if mask(k) != masked]
    removed = len(kept) != len(lst)
    d[provider] = kept
    _save_store(d)
    rebuild_pools()
    return removed


class _Key:
    __slots__ = ("value", "label", "hits", "cooldown_until", "enabled")

    def __init__(self, value: str):
        self.value = value
        self.label = mask(value)
        self.hits = deque()            # request timestamps within the rolling window
        self.cooldown_until = 0.0
        self.enabled = True


class KeyPool:
    """A provider's keys with least-loaded selection + per-key rate accounting."""

    def __init__(self, provider: str, keys: list, rpm: int = _DEFAULT_RPM):
        self.provider = provider
        self.keys = [_Key(k) for k in keys]
        self.rpm = max(1, rpm)
        self.window = _WINDOW
        self.lock = threading.Lock()

    def __bool__(self):
        return bool(self.keys)

    def _usage(self, key: _Key, now: float) -> int:
        while key.hits and now - key.hits[0] > self.window:
            key.hits.popleft()
        return len(key.hits)

    def acquire(self, max_wait: float = _MAX_WAIT):
        """Pick the key with the most headroom; pace-wait if all are at the limit.
        Returns a _Key (record a hit) or None if the pool is empty. Never blocks
        longer than max_wait — then it uses the least-loaded key and lets the
        provider 429 if it must (which we then handle by rotating/cooling down)."""
        if not self.keys:
            return None
        deadline = time.time() + max_wait
        while True:
            now = time.time()
            with self.lock:
                ready = [k for k in self.keys if k.enabled and now >= k.cooldown_until]
                if ready:
                    best = min(ready, key=lambda k: self._usage(k, now))
                    if self._usage(best, now) < self.rpm:
                        best.hits.append(now)
                        return best
                    wait = self.window - (now - best.hits[0])      # until a slot frees
                else:
                    nxt = min((k.cooldown_until for k in self.keys if k.enabled), default=now + 1)
                    wait = nxt - now
            if time.time() >= deadline:
                with self.lock:                                    # give up waiting; use least-loaded
                    pool = [k for k in self.keys if k.enabled] or self.keys
                    best = min(pool, key=lambda k: self._usage(k, time.time()))
                    best.hits.append(time.time())
                    return best
            time.sleep(min(max(wait, 0.05), 0.5))

    def penalize(self, key: _Key, cooldown: float = _COOLDOWN):
        """Bench a key briefly after a rate-limit / transient error."""
        if key:
            with self.lock:
                key.cooldown_until = time.time() + cooldown

    def disable(self, key: _Key):
        """Take a key out of rotation (e.g. it auth-failed — a bad key)."""
        if key:
            with self.lock:
                key.enabled = False

    def report(self) -> list:
        """Per-key health for the UI (no secrets)."""
        now = time.time()
        with self.lock:
            return [{"key": k.label, "used": self._usage(k, now), "rpm": self.rpm,
                     "enabled": k.enabled,
                     "cooldown_s": max(0, round(k.cooldown_until - now, 1))}
                    for k in self.keys]


# ---- global per-provider pool registry --------------------------------------
_POOLS = {}
_LOCK = threading.Lock()


def get_pool(provider: str):
    """The pool for a provider, built once from the environment. None if the
    provider uses no key (e.g. local ollama) or is unknown."""
    base = _PROVIDER_ENV.get(provider)
    if not base:
        return None
    with _LOCK:
        pool = _POOLS.get(provider)
        if pool is None:
            pool = KeyPool(provider, _discover_keys(base, provider))
            _POOLS[provider] = pool
        return pool


def pool_for_model(model: str):
    return get_pool(provider_of(model))


def rebuild_pools():
    """Forget cached pools so the next call re-reads keys from the env (used when
    keys change at runtime, e.g. via the future Settings UI)."""
    with _LOCK:
        _POOLS.clear()


def report_all() -> dict:
    """All provider pools' health, for the UI/usage view."""
    out = {}
    for prov, base in _PROVIDER_ENV.items():
        pool = get_pool(prov)
        if pool and pool.keys:
            out[prov] = pool.report()
    return out

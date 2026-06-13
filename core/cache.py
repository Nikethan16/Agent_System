"""
cache.py — a tiny, thread-safe TTL cache for expensive DETERMINISTIC results.

WHY: on the rate-limited free tier, repeating identical work wastes the scarce
requests-per-minute. Identical web fetches, document parses, and embeddings are
served from memory instead of re-calling the network / provider, which cuts both
latency and API calls. (Classification is already cached in core/router.py.)

Stdlib only; stays in core (offline — a cache touches no provider/model/web). In-memory
per process (cleared on restart) — the right scope for a local single-user tool, and it
keeps the implementation simple and dependency-free.
"""
import os
import time
import hashlib
import threading

_DEFAULT_TTL = float(os.environ.get("AGENT_CACHE_TTL", "3600"))      # 1 hour
_MAX_ENTRIES = int(os.environ.get("AGENT_CACHE_MAX", "512"))


def key_for(*parts) -> str:
    """A stable cache key from arbitrary string parts (hashed so it stays short)."""
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8", "replace")).hexdigest()


class TTLCache:
    """A bounded, thread-safe key->value cache with per-entry expiry + hit/miss stats."""

    def __init__(self, ttl: float = _DEFAULT_TTL, max_entries: int = _MAX_ENTRIES):
        self.ttl = ttl
        self.max = max(1, max_entries)
        self._d: dict[str, tuple] = {}        # key -> (expires_at, value)
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        now = time.time()
        with self._lock:
            item = self._d.get(key)
            if item and item[0] > now:
                self.hits += 1
                return item[1]
            if item:                          # expired — drop it
                self._d.pop(key, None)
            self.misses += 1
            return None

    def put(self, key: str, value, ttl: float = None) -> None:
        exp = time.time() + (self.ttl if ttl is None else ttl)
        with self._lock:
            if key not in self._d and len(self._d) >= self.max:
                # evict the entry that expires soonest (approx-LRU by deadline)
                oldest = min(self._d, key=lambda k: self._d[k][0])
                self._d.pop(oldest, None)
            self._d[key] = (exp, value)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {"entries": len(self._d), "hits": self.hits, "misses": self.misses,
                    "hit_rate": round(self.hits / total, 3) if total else 0.0}


# ---- named-cache registry (so the health view can report all of them) -------
_CACHES: dict[str, TTLCache] = {}
_REG_LOCK = threading.Lock()


def get_cache(name: str, ttl: float = None, max_entries: int = None) -> TTLCache:
    """The named cache, created once. Callers keep a reference and use get()/put()."""
    with _REG_LOCK:
        c = _CACHES.get(name)
        if c is None:
            c = TTLCache(ttl=ttl if ttl is not None else _DEFAULT_TTL,
                         max_entries=max_entries if max_entries is not None else _MAX_ENTRIES)
            _CACHES[name] = c
        return c


def all_stats() -> dict:
    """Per-cache stats for the Model Health view."""
    with _REG_LOCK:
        return {name: c.stats() for name, c in _CACHES.items()}


def clear_all() -> None:
    with _REG_LOCK:
        for c in _CACHES.values():
            c.clear()

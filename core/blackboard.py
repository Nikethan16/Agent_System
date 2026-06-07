"""
blackboard.py — the shared per-run scratchpad agents collaborate through.

This is how agents "talk to each other" safely: instead of free-form agent->agent
messages (which can loop and burn budget), the supervisor coordinates and each agent
posts its findings/artifacts here; downstream agents read what they need. Predictable,
budget-capped, and easy to trace.
"""
import threading
from dataclasses import dataclass, field


@dataclass
class Entry:
    agent: str
    key: str
    content: str


@dataclass
class Blackboard:
    entries: list = field(default_factory=list)

    def __post_init__(self):
        self._lock = threading.Lock()

    def post(self, agent: str, key: str, content) -> None:
        with self._lock:                       # thread-safe for parallel subtasks
            self.entries.append(Entry(agent, key, str(content)))

    def read(self, keys=None) -> str:
        items = self.entries if keys is None else [e for e in self.entries if e.key in keys]
        return "\n\n".join(f"[{e.agent} · {e.key}]\n{e.content}" for e in items)

    def digest(self, limit: int = 6000) -> str:
        """A bounded view of everything posted so far (for agent context)."""
        text = self.read()
        return text if len(text) <= limit else text[:limit] + "\n…(truncated)"

    def as_list(self) -> list:
        return [{"agent": e.agent, "key": e.key, "content": e.content} for e in self.entries]

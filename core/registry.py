"""
registry.py — loads config/models.yaml and resolves tier -> model.

This is the abstraction that makes models swappable. Nothing else in the core
hardcodes a model name; everything asks the registry.

Two resolution strategies (defaults.model_strategy in models.yaml):
  * "fixed"    — each tier uses its configured `model:` (the classic behaviour).
  * "cheapest" — pick the CHEAPEST catalog model that is (a) capable enough for the
    tier and (b) AVAILABLE (its required provider key is set). As you add free
    providers' keys, cheaper/free models unlock and get chosen automatically. This is
    the cost-first mode.

The catalog = the models.yaml `catalog:` PLUS any models the model-scout agent has
discovered (config/models.discovered.yaml). Add/remove of discovered models is done
via the registry (update_catalog / remove_from_catalog), so the curated, commented
models.yaml stays pristine.
"""
import os
import json
import logging
import threading
import yaml

log = logging.getLogger(__name__)

_DIR = os.path.dirname(__file__)
_DEFAULT_PATH = os.path.join(_DIR, "..", "config", "models.yaml")
CONFIG_PATH = os.environ.get("MODELS_CONFIG", _DEFAULT_PATH)
DISCOVERED_PATH = os.environ.get(
    "MODELS_DISCOVERED", os.path.join(_DIR, "..", "config", "models.discovered.yaml"))
# UI-editable routing overrides (gitignored); merged over models.yaml `routing:`.
ROUTING_PATH = os.environ.get(
    "ROUTING_OVERRIDE",
    os.path.join(os.environ.get("DATA_DIR", os.path.join(_DIR, "..", "data")), "routing.json"))


class ModelRegistry:
    def __init__(self, path: str = CONFIG_PATH):
        self.path = path
        self._lock = threading.Lock()
        self.reload()

    def reload(self):
        with open(self.path) as f:
            self.cfg = yaml.safe_load(f)
        self._discovered = self._load_discovered()
        self._routing_override = self._load_routing_override()

    def _load_routing_override(self) -> dict:
        try:
            with open(ROUTING_PATH) as f:
                return json.load(f) or {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            log.warning("could not load routing override from %s: %s", ROUTING_PATH, e)
            return {}

    def _load_discovered(self):
        try:
            with open(DISCOVERED_PATH) as f:
                data = yaml.safe_load(f) or {}
            return data.get("catalog", []) or []
        except FileNotFoundError:
            return []
        except Exception as e:
            log.warning("could not load discovered models from %s: %s", DISCOVERED_PATH, e)
            return []

    # ---- tier resolution -------------------------------------------------
    def tier(self, name: str) -> dict:
        return self.cfg["tiers"][name]

    def model_for_tier(self, name: str, task_type: str = None) -> str:
        if self.model_strategy() == "cheapest":
            return self.model_chain(name, task_type, max_len=1)[0]
        return self.cfg["tiers"][name]["model"]

    def max_tokens_for_tier(self, name: str) -> int:
        return self.cfg["tiers"][name].get("max_tokens", 4096)

    # ---- context-window awareness (replaces the old hardcoded 12-message window) ----
    def context_window_for(self, model_id: str) -> int:
        """The input context window (tokens) for a model — from its catalog entry's
        `context_window`, else defaults.context_window, else a safe floor."""
        m = self._by_id(model_id) if model_id else None
        if m and m.get("context_window"):
            try:
                return int(m["context_window"])
            except (TypeError, ValueError):
                pass
        return int(self.cfg.get("defaults", {}).get("context_window", 32000))

    def context_budget(self) -> int:
        """A safe INPUT-token budget for assembling a turn's context. Uses the SMALLEST
        context window among AVAILABLE models (so we never overflow whatever the router
        picks), at ~60%, minus headroom for the answer + tool schemas. This is what makes
        history adaptive: a 128K+ fleet gets tens of thousands of tokens of context, not
        an arbitrary 12 messages — and a tiny local model automatically gets less.

        Capped by AGENT_MAX_CONTEXT_TOKENS (default 24000): on a 128K/1M fleet the 60%
        figure is ~70K+ tokens of verbatim history re-sent EVERY round, which is costly
        with little marginal benefit (cross-session memory recall already supplies older
        facts). The cap keeps plenty of recent history while cutting input cost; raise it
        for very long-context workflows."""
        # Read each model's window straight from its catalog entry instead of calling
        # context_window_for() (which does a linear _by_id scan) per model — that made
        # this O(catalog^2), and it runs every turn (context assembly) + every
        # compaction check. This is O(catalog).
        default_win = int(self.cfg.get("defaults", {}).get("context_window", 32000))
        wins = []
        for m in self.catalog():
            if not self._available(m):
                continue
            cw = m.get("context_window")
            try:
                wins.append(int(cw) if cw else default_win)
            except (TypeError, ValueError):
                wins.append(default_win)
        floor = min(wins) if wins else default_win
        budget = max(4000, int(floor * 0.6) - 8192)
        try:
            cap = int(os.environ.get("AGENT_MAX_CONTEXT_TOKENS", "24000"))
        except (TypeError, ValueError):
            cap = 24000
        return min(budget, cap) if cap > 0 else budget

    def classifier_tier(self) -> str:
        return self.cfg["defaults"]["classifier_tier"]

    def fallback_tier(self) -> str:
        return self.cfg["defaults"]["fallback_tier"]

    def worker_tier(self) -> str:
        return self.cfg.get("worker_tier", "tier2")

    def model_strategy(self) -> str:
        return self.cfg.get("defaults", {}).get("model_strategy", "fixed")

    # ---- catalog (base + discovered) ------------------------------------
    def catalog(self) -> list:
        base = self.cfg.get("catalog", []) or []
        by_id = {m["id"]: m for m in base}
        for m in self._discovered:                 # discovered overrides/extends base
            by_id[m["id"]] = m
        return list(by_id.values())

    def sampling_for(self, model: str) -> dict:
        """Per-model sampling params from the catalog entry's optional `sampling:` block
        (temperature/top_p/top_k/repeat_penalty/min_p). Empty when none is set, so the
        caller keeps its own default. Lets a model that needs e.g. temp 0.55 + a repeat
        penalty (Qwen, to avoid loops) override the generic default WITHOUT a code change;
        LiteLLM drops any keys the provider doesn't support."""
        for m in self.catalog():
            if m.get("id") == model:
                return dict(m.get("sampling") or {})
        return {}

    # ---- cost-first selection -------------------------------------------
    @staticmethod
    def _level(name) -> int:
        s = str(name)
        return int(s[-1]) if s and s[-1].isdigit() else 2

    @staticmethod
    def _available(m: dict) -> bool:
        env = m.get("requires_env")
        return (not env) or bool(os.environ.get(env))

    @staticmethod
    def _cost_key(m: dict):
        # free first, then lowest relative cost
        return (0 if m.get("free") else 1, m.get("cost", 999))

    def ranked_for(self, needed_level: int, task_type: str = None) -> list:
        """All AVAILABLE models capable of this level, ranked cheapest/preferred first.
        If a task_type is given and any candidate is tagged good_for it, restrict to
        those (a specialist wins); otherwise keep every capable model."""
        cands = [m for m in self.catalog()
                 if self._available(m) and m.get("tier_hint", 2) >= needed_level]
        if task_type:
            pref = [m for m in cands if task_type in (m.get("good_for") or [])]
            if pref:
                cands = pref
        cands.sort(key=self._cost_key)
        return [m["id"] for m in cands]

    def cheapest_for(self, needed_level: int, task_type: str = None):
        ranked = self.ranked_for(needed_level, task_type)
        return ranked[0] if ranked else None

    def routing(self) -> dict:
        """Explicit per-task fallback chains: models.yaml `routing:` with any UI-saved
        overrides (data/routing.json) merged on top. Maps task_type -> ordered model ids."""
        base = dict(self.cfg.get("routing") or {})
        base.update(self._routing_override or {})
        return base

    def set_routing(self, task_type: str, chain: list):
        """Persist a UI-edited fallback chain for a task_type (override file)."""
        if not isinstance(chain, list):
            raise ValueError("chain must be a list of model ids")
        with self._lock:
            self._routing_override[task_type] = [str(m) for m in chain if m]
            os.makedirs(os.path.dirname(ROUTING_PATH), exist_ok=True)
            with open(ROUTING_PATH, "w", encoding="utf-8") as f:
                json.dump(self._routing_override, f)
        return self.routing()

    def _by_id(self, mid: str):
        for m in self.catalog():
            if m.get("id") == mid:
                return m
        return None

    def timeout_for_model(self, model: str):
        """Per-model wall-clock timeout (seconds) from the catalog `timeout_s` field, or
        None to use the global default (AGENT_LLM_TIMEOUT). Lets slow frontier reasoning
        models (which take ~70s+ on the free tier) get more headroom than fast models,
        so a non-streaming call to one isn't guillotined by the default 45s wall."""
        try:
            m = self._by_id(model)
            v = (m or {}).get("timeout_s")
            return float(v) if v else None
        except Exception:
            return None

    def model_chain(self, tier: str, task_type: str = None, max_len: int = 4) -> list:
        """The ordered fallback chain for a (tier, task_type): primary first, then
        progressively-broader fallbacks. Used by complete_chain(). Composition:
          1) explicit routing[task_type] override (available + capable), then
          2) auto cost-ranked specialists for this task, then
          3) any other capable model (cross-task safety net),
          4) and finally the fixed-mode tier model so the chain is never empty
             (e.g. offline tests with no provider key set)."""
        level = self._level(tier)
        chain = []

        def _add(mid):
            if mid and mid not in chain:
                chain.append(mid)

        if task_type:
            for mid in self.routing().get(task_type, []) or []:
                m = self._by_id(mid)
                if m and self._available(m) and m.get("tier_hint", 2) >= level:
                    _add(mid)
        for mid in self.ranked_for(level, task_type):
            _add(mid)
        for mid in self.ranked_for(level, None):        # deeper, cross-task fallbacks
            _add(mid)
        if not chain:
            _add(self.cfg["tiers"][tier]["model"])
        return chain[:max_len]

    # ---- live swap (used by the UI) -------------------------------------
    def set_tier_model(self, tier: str, model: str):
        with self._lock:
            if tier not in self.cfg["tiers"]:
                raise KeyError(f"unknown tier: {tier}")
            self.cfg["tiers"][tier]["model"] = model
        return self.cfg["tiers"][tier]

    # ---- catalog curation (the model-scout writes here) -----------------
    def _save_discovered(self):
        with open(DISCOVERED_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump({"catalog": self._discovered}, f, sort_keys=False)

    # Only these keys are persisted from a (possibly LLM- or client-supplied) entry,
    # each coerced to a safe type — so a malformed/hostile proposal can't inject
    # arbitrary fields that later get treated as config.
    @staticmethod
    def _clean_entry(m: dict):
        mid = m.get("id")
        if not isinstance(mid, str) or not mid.strip() or len(mid) > 200:
            return None
        out = {"id": mid.strip()}
        if isinstance(m.get("provider"), str):
            out["provider"] = m["provider"][:80]
        if isinstance(m.get("requires_env"), str):
            out["requires_env"] = m["requires_env"][:80]
        out["free"] = bool(m.get("free", False))
        out["open_source"] = bool(m.get("open_source", False))
        try:
            out["cost"] = max(0, int(m.get("cost", 999)))
        except (TypeError, ValueError):
            out["cost"] = 999
        try:
            out["tier_hint"] = min(3, max(1, int(m.get("tier_hint", 2))))
        except (TypeError, ValueError):
            out["tier_hint"] = 2
        gf = m.get("good_for") or []
        out["good_for"] = [str(x)[:40] for x in gf if isinstance(x, (str, int))][:20] \
            if isinstance(gf, list) else []
        return out

    def update_catalog(self, models: list):
        """Add/replace discovered models (by id). Validates + persists + reloads."""
        if not isinstance(models, list):
            raise ValueError("models must be a list")
        with self._lock:
            by_id = {m["id"]: m for m in self._discovered}
            for raw in models:
                if not isinstance(raw, dict):
                    continue
                clean = self._clean_entry(raw)
                if clean:
                    by_id[clean["id"]] = clean
            self._discovered = list(by_id.values())
            self._save_discovered()
        return self.catalog()

    def remove_from_catalog(self, model_id: str):
        with self._lock:
            self._discovered = [m for m in self._discovered if m["id"] != model_id]
            self._save_discovered()
        return self.catalog()


# single shared instance
registry = ModelRegistry()

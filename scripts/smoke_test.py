"""
smoke_test.py — offline regression checks for the whole platform.

Runs the real pipeline with a FAKE model (no API keys, no cost) and asserts the key
behaviours still work end-to-end. Exit code is non-zero on any failure, so this works
as a CI gate alongside `python -m evals --dry-run`.

    python scripts/smoke_test.py
"""
import os
import sys
import time

# Allow running as `python scripts/smoke_test.py` from the project root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Isolate test data so we never touch the user's real ./data. Start FRESH each run
# (only wiping the dir WE chose, never a user-supplied DATA_DIR) so persisted rows
# — e.g. approved procedural rules — can't leak between runs and break assertions.
_smoke_owned = "DATA_DIR" not in os.environ
os.environ.setdefault("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data", "_smoke"))
if _smoke_owned:
    import shutil
    shutil.rmtree(os.environ["DATA_DIR"], ignore_errors=True)
os.environ.setdefault("AUDIT_LOG", os.path.join(os.environ["DATA_DIR"], "audit.log"))
# The API now requires a token for non-loopback callers (TestClient's host is
# "testclient", not 127.0.0.1), so configure one and send it on every request below.
os.environ.setdefault("AGENT_AUTH_TOKEN", "smoke-token")
_AUTH_HEADERS = {"X-Auth-Token": os.environ["AGENT_AUTH_TOKEN"]}

import core.llm as L
from core.llm import Budget, BudgetExceeded


# ---- fake model -------------------------------------------------------------
class _Msg:
    def __init__(self, c, tc=None):
        self.content = c
        self.tool_calls = tc

    def model_dump(self):
        return {"role": "assistant", "content": self.content}


class _Resp:
    def __init__(self, c):
        self.choices = [type("C", (), {"message": _Msg(c)})()]
        self._hidden_params = {"response_cost": 0.0}


class _Chunk:
    def __init__(self, c):
        self.choices = [type("C", (), {"delta": type("D", (), {"content": c, "tool_calls": None})()})()]
        self.usage = None


class _TC:
    def __init__(self, n, a):
        self.id = "t"
        self.function = type("F", (), {"name": n, "arguments": a})()


def _ToolResp(content, calls):
    m = _Msg(content, [_TC(n, a) for n, a in calls])
    return type("R", (), {"choices": [type("C", (), {"message": m})()], "_hidden_params": {"response_cost": 0.0}})()


_REVIEW = {"n": 0}
_MASTER = {"n": 0}


def fake(**kw):
    if kw.get("stream"):
        return iter([_Chunk("final "), _Chunk("answer.")])
    msgs = kw.get("messages", [])
    sysm = next((m.get("content", "") for m in msgs if m.get("role") == "system"), "").lower()
    user = next((m.get("content", "") for m in msgs if m.get("role") == "user"), "")
    if "task router" in sysm:
        tier = 3 if "build" in user.lower() else 1
        return _Resp('{"tier": %d, "task_type":"coding","requires_web":false,"reason":"x"}' % tier)
    if "lead engineer coordinating" in sysm:      # the master loop
        _MASTER["n"] += 1
        if _MASTER["n"] == 1:
            return _ToolResp("Planning.", [("write_todos", '{"todos":[{"text":"write code","status":"pending"}]}')])
        if _MASTER["n"] == 2:
            return _ToolResp("Delegating.", [("delegate", '{"agent":"coder","instruction":"write the code"}')])
        return _Resp("Done — built it via the coder.")
    if "extract durable facts" in sysm:            # semantic memory extractor
        return _Resp('{"facts":[{"key":"language","value":"Python"},{"key":"name","value":"Sam"}]}')
    if "running summary" in sysm:                  # working-memory summarizer
        return _Resp("Summary: Sam uses Python and is building an agent system.")
    if "reusable working rule" in sysm:            # procedural rule proposer
        return _Resp('{"rules":["Run the test suite before declaring a coding task done."]}')
    if "agent dispatcher" in sysm:
        return _Resp('{"agent":"coder","reason":"x"}')
    if "strict qa reviewer" in sysm:
        _REVIEW["n"] += 1
        return _Resp('{"pass": %s, "issues":["x"], "summary":"checked"}' % ("false" if _REVIEW["n"] == 1 else "true"))
    if "fix them" in user:
        return _Resp("[fixed]")
    return _Resp("[done]")


L.litellm.completion = fake

PASS, FAIL = [], []


def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


# ---- core / orchestrator ----------------------------------------------------
import core.orchestrator as orch
from core import toolbelt, policy
import tools  # noqa: F401  (registers MCP example + web/image tools)

print("\n[core / platform]")
rb = toolbelt.get("run_bash")
check("policy blocks rm -rf /", policy.evaluate(rb, {"command": "rm -rf /"}).action == "block")
check("policy escalates DROP TABLE (human)", policy.evaluate(rb, {"command": "DROP TABLE u"}).requires_human)
check("MCP example tools registered", "mcp__example__echo" in toolbelt.names())

# ---- surgical edit tool (Path B harness upgrade) ----------------------------
import tempfile
from core import tools as _T
check("edit_file registered as a tool", "edit_file" in toolbelt.names())
with _T.using_workspace(tempfile.mkdtemp()):
    _T.write_file("e.py", "a = 1\nb = 2\n")
    _T.edit_file("e.py", "a = 1", "a = 100")
    _ec = _T.read_file("e.py")
    check("edit_file replaces an exact snippet", "a = 100" in _ec and "a = 1\n" not in _ec)
    check("edit_file errors on a missing snippet", _T.edit_file("e.py", "NOPE", "x").startswith("ERROR"))
    _T.write_file("d.py", "x\nx\n")
    check("edit_file refuses an ambiguous match", "unique" in _T.edit_file("d.py", "x", "y").lower())
    _T.edit_file("d.py", "x", "y", replace_all=True)
    check("edit_file replace_all replaces every occurrence", _T.read_file("d.py").count("y") == 2)
    check("edit_file errors when file is missing", _T.edit_file("missing.py", "a", "b").startswith("ERROR"))
from core import agents as _team
check("edit_file granted to the coder agent", "edit_file" in _team.agents.get("coder").tools)

ev = []
final = orch.handle_task("write a function", emit=ev.append, review=True)
check("simple path returns final", bool(final))
check("critic ran + retried (fixed)", final == "[fixed]" and _REVIEW["n"] >= 1)

ev = []
final = orch.handle_task("build a multi part thing", emit=ev.append)
assigns = [e.get("agent") for e in ev if e["type"] == "assign"]
todos_emitted = any(e.get("type") == "plan" and e.get("todos") for e in ev)
check("lead master loop wrote a todo list", todos_emitted)
check("lead delegated to a specialist (coder)", "coder" in assigns)
check("lead produced a final answer", bool(final))

# ---- auto-review decision (A5) ----
check("auto-review on for complex (tier3)", orch._auto_review(3, "research") is True)
check("auto-review on for tier2 coding", orch._auto_review(2, "coding") is True)
check("auto-review off for trivial (tier1)", orch._auto_review(1, "coding") is False)
check("auto-review off for tier2 lookup", orch._auto_review(2, "research") is False)
check("resolve-review honours explicit False", orch._resolve_review(False, 3, "coding") is False)

# ---- resilience: key pool + fallback chains (Phase 2) -----------------------
print("\n[core / resilience]")
from core import keypool as KP
check("provider_of detects nvidia_nim",
      KP.provider_of("nvidia_nim/deepseek-ai/deepseek-v4-pro") == "nvidia_nim")
check("provider_of detects bare openai/anthropic",
      KP.provider_of("gpt-5.5") == "openai" and KP.provider_of("claude-x") == "anthropic")
_pool = KP.KeyPool("test", ["key1aaaaaaaa", "key2bbbbbbbb"], rpm=3)
_k1, _k2 = _pool.acquire(max_wait=0), _pool.acquire(max_wait=0)
check("keypool spreads load across keys (least-loaded)", _k1.value != _k2.value)
for _ in range(8):
    _pool.acquire(max_wait=0)            # max_wait=0 never sleeps (uses least-loaded)
check("keypool rate accounting tracks usage", sum(r["used"] for r in _pool.report()) >= 5)
check("keypool masks keys (no secret leak)", all("…" in r["key"] for r in _pool.report()))
_pool.penalize(_k1)
check("keypool penalize benches a key (cooldown)", any(r["cooldown_s"] > 0 for r in _pool.report()))
_pool.disable(_k2)
check("keypool disable removes a bad key", any(not r["enabled"] for r in _pool.report()))

# model_chain: with a provider key present, routing picks the configured primary.
import os as _os
from core.registry import registry as _reg
_os.environ["NVIDIA_NIM_API_KEY"] = "smoke-nvidia-key"   # make NVIDIA models "available"
try:
    _chain = _reg.model_chain("tier3", task_type="reasoning")
    check("model_chain returns an ordered fallback list", isinstance(_chain, list) and len(_chain) >= 2)
    check("model_chain routing: reasoning primary = deepseek-v4-pro",
          _chain[0] == "nvidia_nim/deepseek-ai/deepseek-v4-pro")
    check("model_chain routing: coding primary = glm-5.1",
          _reg.model_chain("tier2", task_type="coding")[0] == "nvidia_nim/z-ai/glm-5.1")
    check("model_chain has no duplicates", len(_chain) == len(set(_chain)))
finally:
    _os.environ.pop("NVIDIA_NIM_API_KEY", None)

# complete_chain: falls back to the next model when one fails (+ emits a fallback event).
_seen, _fbev = [], []
def _chain_fake(**kw):
    _seen.append(kw.get("model"))
    if kw.get("model") == "m-bad":
        raise RuntimeError("simulated provider outage")
    return _Resp("ok from " + kw.get("model"))
L.litellm.completion = _chain_fake
_r, _ = L.complete_chain(["m-bad", "m-good"], [{"role": "user", "content": "hi"}],
                         budget=Budget(max_usd=1, max_iterations=5),
                         on_fallback=lambda f, t, w: _fbev.append((f, t)))
check("complete_chain falls back to the next model on failure",
      _r.choices[0].message.content == "ok from m-good")
check("complete_chain emitted a fallback event", _fbev == [("m-bad", "m-good")])
# ...but a BudgetExceeded is a hard stop — never a fallback trigger.
_overb = Budget(max_usd=0.01, max_iterations=5)
_overb.add_cost(0.02)
_stopped = False
try:
    L.complete_chain(["m-good", "m-good2"], [{"role": "user", "content": "hi"}], budget=_overb)
except BudgetExceeded:
    _stopped = True
check("complete_chain does NOT fall back past the budget cap", _stopped)
L.litellm.completion = fake   # restore for the rest of the suite

# ---- skills ----
from core import skills as sk
from core import agents as team_mod
chosen = sk.select("write a python function with tests")
check("skill selection finds python-project", any(s.name == "python-project" for s in chosen))
# document skills imported + selected by distinctive trigger words (A1/A2)
names = [c["name"] for c in sk.catalog()]
check("document skills imported (docx/xlsx/pptx/pdf)", all(n in names for n in ("docx", "xlsx", "pptx", "pdf")))
check("deck -> pptx skill", any(s.name == "pptx" for s in sk.select("make a slide deck for Q3")))
check("spreadsheet -> xlsx skill", any(s.name == "xlsx" for s in sk.select("a spreadsheet of expenses")))
check("explicit skill name is force-loaded", any(s.name == "pdf" for s in sk.select("do the thing", names=["pdf"])))
check("no false-positive skill on plain chat", sk.select("explain how recursion works") == [])
cap = {"msgs": None}
def _fake_capture(**kw):
    cap["msgs"] = kw.get("messages")
    return _Resp("done")
L.litellm.completion = _fake_capture
team_mod.run("coder", "write a python function with tests and run them", budget=Budget(max_usd=1, max_iterations=4))
L.litellm.completion = fake   # restore for the rest of the suite
joined = " ".join(m.get("content", "") for m in (cap["msgs"] or []))
check("skill guidance injected into the agent", "python-project" in joined and "production-quality Python" in joined)

# sub-budget
parent = Budget(max_usd=1.0, max_iterations=100)
child = parent.child(max_usd=0.05)
child.add_cost(0.06)
tripped = False
try:
    child.check()
except BudgetExceeded:
    tripped = True
check("sub-budget caps locally", tripped)
check("sub-budget forwards to parent", parent.spent_usd >= 0.06)

# ---- memory: semantic facts + working summary (A + B) -----------------------
from server import db as _db, memory as MEM
_db.init_db()   # ensure tables exist (server.app, which normally does this, loads later)
MEM.extract_facts("My name is Sam and I build in Python.", scope="global",
                  budget=Budget(max_usd=1, max_iterations=5))
_facts = MEM.list_facts()
check("semantic: facts extracted", any(f["key"] == "language" for f in _facts))
check("semantic: facts deduped by key", len([f for f in _facts if f["key"] == "language"]) == 1)
check("semantic: facts injectable by scope", any("Python" in t for t in MEM.get_facts(["global"])))
MEM.update_summary("smoke-sess", [{"role": "user", "content": "built a calculator"}],
                   budget=Budget(max_usd=1, max_iterations=5))
check("working: rolling summary written", "summary" in MEM.get_summary("smoke-sess").lower())
_fid = _facts[0]["id"]
check("memory: forget works", MEM.forget_fact(_fid) and not any(f["id"] == _fid for f in MEM.list_facts()))

# ---- Phase C: embedding-based semantic recall -------------------------------
_oem, _ovec = MEM._embed_model, MEM._vec
MEM._embed_model = lambda: "fake-embed"
MEM._vec = lambda t: [1.0, 0.0] if "calculator" in (t or "").lower() else [0.0, 1.0]
MEM.remember("Request: build a calculator\nOutcome: calc.py", session_id="emb1", kind="turn")
MEM.remember("Request: write a poem\nOutcome: poem.txt", session_id="emb1", kind="turn")
_hits = MEM.recall("please help me with a calculator app", k=2, exclude_session="zzz")
check("semantic recall (embeddings) finds by meaning", any("calculator" in h for h in _hits))
check("semantic recall excludes unrelated note", not any("poem" in h for h in _hits))
MEM._embed_model, MEM._vec = _oem, _ovec

# ---- Phase D: procedural rules (propose -> approve -> active) ----------------
MEM.propose_rule("write a parser", "built parser.py and ran its tests",
                 scope="global", budget=Budget(max_usd=1, max_iterations=5))
_proposed = MEM.list_rules("proposed")
check("procedural: rule proposed for review", len(_proposed) >= 1)
check("procedural: proposed rule is NOT yet active", not MEM.get_active_rules(["global"]))
_rid = _proposed[0]["id"]
check("procedural: approve promotes to active", MEM.approve_rule(_rid)
      and any("test suite" in r for r in MEM.get_active_rules(["global"])))
check("procedural: delete removes the rule", MEM.delete_rule(_rid)
      and not any(x["id"] == _rid for x in MEM.list_rules()))

# ---- memory & context continuity (Phase 3) ----------------------------------
print("\n[memory / continuity]")
from core.registry import registry as _reg3
check("context_budget is a sane positive token budget", _reg3.context_budget() >= 4000)
check("context_window_for falls back to the default", _reg3.context_window_for("unknown/x") >= 8000)
# structured, resumable project state
MEM.set_state("project:smoke", {"goal": "build the app",
              "plan": [{"text": "phase 1", "status": "done"},
                       {"text": "phase 2", "status": "done"},
                       {"text": "phase 3", "status": "pending"}],
              "next": "phase 3", "artifacts": ["app.py"]})
_st = MEM.get_state("project:smoke")
check("project state round-trips", _st.get("goal") == "build the app" and len(_st["plan"]) == 3)
_sc = MEM.state_context("project:smoke")
check("state_context renders a RESUME roadmap", "RESUME" in _sc and "[x] phase 1" in _sc and "phase 3" in _sc)
check("state_context empty for an unknown scope", MEM.state_context("project:none") == "")
check("clear_state removes it", MEM.clear_state("project:smoke") and MEM.get_state("project:smoke") == {})
# project-shared vs per-session workspace (continuity)
from server import projects as _proj
_pp = _proj.create("smoke project")
_pchat = _db.create_session("proj chat", project_id=_pp["id"])
check("workspace is PROJECT-shared for a project chat",
      ("project_" + _pp["id"]) in _db.session_workspace(_pchat.id).replace("\\", "/"))
_solo = _db.create_session("solo chat")
check("workspace is per-session for a standalone chat",
      _solo.id in _db.session_workspace(_solo.id) and "project_" not in _db.session_workspace(_solo.id))
# token-budgeted history packing (replaces the hardcoded 12)
import server.chat as _CH
check("history packing is token-budgeted (not a fixed 12)",
      _CH._approx_tokens("x" * 400) >= 90 and callable(_CH._recent_history_budgeted))

# ---- global daily spend cap -------------------------------------------------
from server import spend as SP
SP.record(0.10)
check("spend: records daily total", SP.spent_today() >= 0.10)
SP.DAILY_CAP = 0.05
check("spend: over_cap trips when day's spend exceeds the cap", SP.over_cap() is True)
SP.DAILY_CAP = 0.0
check("spend: unlimited (no refusal) when cap is 0", SP.over_cap() is False)

# ---- model benchmark (Model Lab) — dry-run subprocess exercises the whole flow
from server import benchmark as BM
check("benchmark aspects load", set(BM.aspects()) >= {"coding", "reasoning", "writing", "instruction"})
_bid = BM.start_run("dry-run-model", "both", dry_run=True)
_br = None
for _ in range(180):
    _br = BM.get_run(_bid)
    if _br and _br["status"] in ("done", "error"):
        break
    time.sleep(0.5)
check("benchmark run completes", bool(_br) and _br["status"] == "done")
_sc = (_br or {}).get("result", {}).get("scores", {})
check("benchmark scorecard has per-aspect raw + pipeline scores",
      "coding" in _sc.get("raw", {}) and "coding" in _sc.get("pipeline", {}))

# ---- server (REST + queue + diff + memory) ----------------------------------
print("\n[server / app]")
from fastapi.testclient import TestClient
from server.app import app
from server import db, memory

with TestClient(app, headers=_AUTH_HEADERS) as c:
    check("health ok", c.get("/api/health").json().get("ok") is True)
    # auth gate: a request WITHOUT the token must be rejected (401)
    check("API rejects missing token", c.get("/api/sessions", headers={"X-Auth-Token": ""}).status_code == 401)
    sid = c.post("/api/sessions", json={"title": "smoke"}).json()["id"]

    ws = db.session_workspace(sid)
    open(os.path.join(ws, "a.py"), "w").write("x=1\n")
    db.create_checkpoint(sid, "before")
    open(os.path.join(ws, "a.py"), "w").write("x=1\ny=2\n")
    d = c.get(f"/api/sessions/{sid}/file/diff", params={"path": "a.py"}).json()
    check("diff detects change", d["changed"] and "+y=2" in d["diff"])

    memory.remember("Request: build a calculator\nOutcome: calc.py", session_id="other")
    check("memory recall works", bool(memory.recall("calculator", exclude_session=sid)))

    jid = c.post("/api/enqueue", json={"session_id": sid, "text": "do work"}).json()["id"]
    status = None
    for _ in range(60):
        status = c.get(f"/api/jobs/{jid}").json()["status"]
        if status in ("done", "error"):
            break
        time.sleep(0.2)
    check("queued job completed", status == "done")

    # memory API: the job's turn extracted facts; list + forget them
    facts = c.get("/api/memory").json()
    check("memory API lists facts", isinstance(facts, list) and len(facts) >= 1)
    fid = facts[0]["id"]
    r = c.delete(f"/api/memory/{fid}")
    check("memory API forget works", r.status_code == 200 and all(f["id"] != fid for f in r.json()["facts"]))
    check("memory API 404 on missing fact", c.delete("/api/memory/nope").status_code == 404)

    # rules API: add (active), propose+approve, delete
    add = c.post("/api/memory/rules", json={"text": "Prefer small, focused functions."}).json()
    check("rules API add (active)", any(x["status"] == "active" and "small" in x["text"] for x in add["rules"]))
    pid = MEM.add_rule("Always write a short README.", scope="global", proposed=True)
    ar = c.post(f"/api/memory/rules/{pid}/approve").json()
    check("rules API approve promotes proposed", any(x["id"] == pid and x["status"] == "active" for x in ar["rules"]))
    check("rules API approve missing -> 404", c.post("/api/memory/rules/nope/approve").status_code == 404)
    dr = c.delete(f"/api/memory/rules/{pid}").json()
    check("rules API delete works", all(x["id"] != pid for x in dr["rules"]))

    sp = c.get("/api/spend").json()
    check("spend API returns status", "spent_today" in sp and "cap" in sp)

    bc = c.get("/api/benchmark/cases").json()
    check("benchmark cases API lists aspects + models", "coding" in bc.get("aspects", {}) and "models" in bc)

    c.delete(f"/api/sessions/{sid}")

# ---- result -----------------------------------------------------------------
print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", ", ".join(FAIL))
    sys.exit(1)
print("ALL SMOKE TESTS PASSED")

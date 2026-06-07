# MODEL REQUIREMENTS — what every model slot must be able to do

Use this to choose models. The system never hard-codes a model; you set a model
string per **tier** in `config/models.yaml` (and a couple of optional standalone
models). Every role below resolves to one of those tiers, so you really only pick
**3 text models (tier1/2/3)** plus **2 optional specialists (image, embeddings)**.

Two hard rules that decide whether a model will work at all:
- **Tool / function-calling is MANDATORY for tier2 and tier3.** The coder, frontend,
  research, QA agents and the tier-3 LEAD loop all call tools via the OpenAI
  function-calling format. A model without reliable function-calling will fail those
  roles (it'll talk instead of acting). This is the single most common reason a model
  "doesn't build anything."
- **Strict JSON / instruction-following for the routing + judgment roles** (router,
  dispatcher, planner, critic, security). They must return small, clean JSON.

---

## The three text tiers — capability profile

### tier1 — "fast & cheap" (the high-volume tier)
Used by: **task router/classifier**, **agent dispatcher**, **fact extraction**,
**rolling chat summaries**. Called on *every* turn, often several times.
Must be able to: follow instructions, emit short strict JSON, classify/summarize.
Does NOT need: deep reasoning, tools, long output.
Optimize for: **lowest latency + highest rate limit + cheap.** This is where
rate-limits hurt most (a slow/limited tier1 stalls every request). Small models are
fine here.

### tier2 — "balanced" (the workers)
Used by: **coder**, **frontend**, **research analyst**, **doc writer**, **critic/QA**,
**general chat**, **security manager**, **model-scout**, **image-prompt crafting**.
Must be able to: **reliable function/tool-calling**, competent **coding** (read→edit→
run→fix), solid **writing/summarization**, and clean JSON for the QA/security roles.
Optimize for: **coding + tool-calling quality** first, then speed. This tier does the
real work; a weak tier2 is the difference between "wrote and ran tests" and "looped".
Needs a decent context window (multi-file edits, fetched pages).

### tier3 — "frontier" (the lead / planner)
Used by: **supervisor/planner** and the **LEAD master loop** (Claude-Code-style:
maintains a todo list, delegates to specialists, uses tools, synthesizes the result).
Must be able to: **strong multi-step reasoning**, **reliable tool-calling across many
rounds**, plan decomposition, and **longer context** (todos + delegated results +
history). This is the most demanding text slot. Reasoning-grade models fit here.

---

## Every role → tier → what the model is actually asked to do

| Role (agent) | Tier slot | Tools it uses | Core capability the model needs |
|---|---|---|---|
| Task router / classifier | tier1 (`classifier_tier`) | none | Short strict JSON, instruction-following, fast |
| Agent dispatcher | tier1 (`dispatcher_tier`) | none | Pick best agent → JSON, fast |
| Fact extraction / chat summary (memory) | tier1 | none | Summarize to terse JSON/text, cheap, high-volume |
| General Assistant | tier2 | none | Natural, accurate chat / writing / explanation |
| Coder | tier2 | read/write/edit/list/**run_bash** | **Coding + reliable tool-calling**, multi-step verify |
| Frontend Engineer | tier2 | read/write/edit/list/run_bash | HTML/CSS/JS/React coding + tool-calling + taste |
| Research Analyst | tier2 | **web_search/web_fetch**/write | Tool-calling + synthesis + citation (needs `SEARCH_API_KEY`) |
| Doc Writer | tier2 | read/write/list | Strong structured **writing** + light tool-use |
| Critic / QA | tier2 | read/list/run_bash | Judgement to **strict pass/fail JSON**, can run tests |
| Security Manager | tier2 | none | Cautious reasoning → approve/deny **JSON** |
| Model Scout (internal) | tier2 | web_search/web_fetch/r/w | Web research → strict JSON (occasional) |
| Supervisor / Planner | tier3 | none | Decompose a goal into ordered subtasks (JSON) |
| LEAD master loop | tier3 | all (delegates) | **Reasoning + many-round tool-calling + long context** |

## Two optional standalone models (only if you use those features)

| Slot | Where you set it | Capability needed | Needed for |
|---|---|---|---|
| **Image model** | `config/models.yaml: image_model:` + provider key | **Text-to-image** generation | the Image Generator agent's `generate_image` |
| **Embedding model** | `.env: EMBED_MODEL=` + provider key | Text **embeddings** (vector output) | semantic (meaning-based) memory recall; falls back to keyword search if unset |

---

## Practical selection guidance (you pick the actual models)

- **You realistically choose 3 text models** (tier1/2/3) in `config/models.yaml`. The
  cost-first selector will use the cheapest *available* model that's capable enough per
  tier, so you can also just drop several into the `catalog:` and let it choose.
- **tier1:** pick the fastest, highest-rate-limit small model you have. JSON-reliable.
  (Latency and rate limit matter more than smarts here.)
- **tier2:** pick your best **coding + function-calling** model — this is the workhorse.
  If you must economize, economize at tier1, not tier2.
- **tier3:** pick a strong **reasoning + tool-calling** model with a large context. Used
  least often (only complex tasks), so a pricier model here is usually fine.
- **Function-calling check:** before trusting a model at tier2/tier3, confirm it supports
  OpenAI-style tool calls in your provider/LiteLLM — otherwise the agents can't act.
- **Rate limits:** a high tier1 limit keeps everyday chat snappy; tier3 builds make many
  calls, so a model with tight per-minute limits will stall multi-step builds.
- **Context window:** tier2 ≥ ~16–32k is comfortable for multi-file work; tier3 benefits
  from more (long todo lists + delegated outputs + history).

## How to apply
Edit the `tiers:` block (or add entries to `catalog:`) in `config/models.yaml`; set
`image_model:` there and `EMBED_MODEL=` in `.env` if you want those. Restart `uvicorn`.
The provider is inferred from the model string prefix (LiteLLM), e.g. `gemini/…`,
`openai/…`, `anthropic/…`, `openrouter/<vendor>/<model>`, `nvidia_nim/…`, `ollama/…`.

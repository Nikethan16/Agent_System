# Model plan — the finalized fleet (2026-07-11)

The durable reference for **which model serves which use case, from where, and why.**
Priority order for every choice: **fit → reliability → cost** (in that order). Prices are
NOT in this doc or in code — they move weekly and live with the provider; only the *shape*
of the plan is stable. The live wiring is `config/models.yaml` (`routing:` + `catalog:`);
this doc explains the intent behind it.

## Keys — two run the whole paid fleet

| Key | Where | Unlocks | Notes |
|-----|-------|---------|-------|
| `DEEPSEEK_API_KEY` | platform.deepseek.com | V4 Pro (plan/lead) + V4 Flash (build/chat) | **Call direct**, not via an aggregator — DeepSeek's automatic prompt cache (~98% off cache-hit input) only stays warm on a stable single-backend prefix. |
| `DEEPINFRA_API_KEY` | deepinfra.com | GLM-4.6 (review/QA), Nemotron-Super (research), Qwen3-Coder (data), Qwen3-VL (vision) | One key, several families, Grade-A SLA. GLM is served FP4 here (cheaper than z.ai's FP8; add z.ai only if the A/B shows FP4 tool-calling faltering). |
| `GEMINI_API_KEY` | aistudio.google.com | Flash-Lite (router/classify), Flash (research fallback) | Near-free; the reliable JSON classifier. |
| `NVIDIA_NIM_API_KEY[_1.._3]` | build.nvidia.com | The **free fallback floor** under every chain | 4 pooled keys, rotated automatically. Free, so it never expires — the safety net when a paid provider is rate-limited/down. |

Everything paid is gated by `requires_env`: with no paid keys, every chain resolves to the
free NIM/Gemini fleet exactly as before — nothing activates until the key lands.

## The assignment (fit → reliability → cost)

| Use case | Primary | Why it fits | Fallbacks |
|----------|---------|-------------|-----------|
| **Plan / lead / math** | DeepSeek **V4 Pro** | frontier reasoning; cheap long outputs (~5× under GLM output price) — planning is reasoning, not tool-calling | Nemotron-Super (DeepInfra) → NIM fleet |
| **Build / code** | DeepSeek **V4 Flash** | community-proven build workhorse; **near-free** in agentic loops via automatic prompt cache | Qwen3-Coder → GLM-4.6 → NIM GLM-5.1 |
| **Review / QA** (`qa`, `review`) | **GLM-4.6** (DeepInfra) | strongest open tool-caller — the reviewer must reliably `run_bash` the tests; short outputs keep cost tiny | V4 Pro → Nemotron → NIM |
| **Research / web** | **Nemotron-Super** (DeepInfra) | first-class tool-caller (our bench 10/10); research is input-heavy with **low** cache hits, so an expensive model burns money here | V4 Flash → Gemini Flash → NIM qwen |
| **Data analysis** | **Qwen3-Coder-480B** (DeepInfra) | code-specialist — data analysis is "code that computes" | V4 Flash → NIM qwen/glm |
| **Chat / general / writing** | DeepSeek **V4 Flash** | fast, coherent, cheap; no tool-calling stakes | GLM-4.6 (writing) → NIM |
| **Router / classify** | **Gemini Flash-Lite** | reliable JSON, sub-second, never the failure point | NIM nemotron-nano |
| **Vision** | **Qwen3-VL** (DeepInfra) | cheapest reliable VLM that also tool-calls | Llama-4-Maverick (NIM) → Gemini |

### Two design rules baked into the chains
1. **Every tool-critical chain spans ≥2 providers**, so one provider's outage can't stall a run.
2. **Paid leads first, then the full curated free order** — so removing a key (or never adding
   one) degrades gracefully to the exact free behavior, losing no benchmarked fallback.

## Why some obvious picks were *not* made
- **GLM for planning** — too expensive on output; V4 Pro reasons as well for ~5× less. GLM is
  reserved for *review/QA* where its tool-calling is the deciding factor and outputs are short.
- **DeepSeek as a tool-using primary** — reasoning-first lineage → weaker structured tool-calls;
  kept for chat/build (build is guarded by the verification gate), not for the QA/review role.
- **z.ai for GLM** — DeepInfra is reliable and cheaper; FP8 (z.ai) is a one-line upgrade if the
  eval A/B shows FP4 GLM missing hard tool-calls. Not paid for on faith.
- **MiniMax / Xiaomi direct** — no zero-retention guarantee; unsafe for proprietary code.

## Prompt caching — the biggest cost lever
In an agentic loop the prompt prefix (system + history + files) repeats every turn, so 90%+ of
input tokens are cache hits at ~2% of list price. This is a **DeepSeek feature available to us
directly** — not a subscription perk. Two things keep it working:
- the agent loop only **appends** (never mutates the prefix) — locked in by `tests/test_cache_friendly.py`;
- real cache reads are surfaced (`prompt_cache_hit_tokens` → run summary "% cached" + Health
  panel) so the savings are visible and can't silently regress.

## Rollout checklist (when a key lands)
1. `python -m scripts.verify_models` — one cheap call per keyed model; confirms the exact
   provider ids are valid (catalogs rename models within weeks).
2. Run `python -m evals` — the swap-safety suite; confirm no quality regression.
3. A/B the open questions on `evals/cases.yaml`: V4-Pro-plan vs GLM-plan, and the
   ported prompt overlays on vs off — let pass-rate decide, per model.

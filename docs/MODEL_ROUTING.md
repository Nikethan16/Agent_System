# Model routing — the finalized fleet (per use case + fallbacks)

The live map of **which model serves which task**, mirrored from `config/models.yaml`
(`routing:`). Chains read **left → right**: the run uses the first model whose provider
**key is present**; if it's rate-limited/down it falls to the next. Key-less models are
auto-skipped, so with **no paid keys the run lands entirely on the free NVIDIA NIM / Gemini
floor** — nothing breaks. Design intent: fit → reliability → cost (see `docs/MODEL_PLAN.md`).

## Routing per use case

| Use case | Primary | Paid fallback(s) | Free floor (NIM / Gemini) |
|---|---|---|---|
| **Chat** | DeepSeek V4-Flash | — | Gemini Flash-Lite → NIM nemotron-nano → NIM GLM-5.1 |
| **General** | DeepSeek V4-Flash | — | NIM GLM-5.1 → NIM Llama-4-Maverick |
| **Writing** | DeepSeek V4-Flash | GLM-5.1 | NIM GLM-5.1 |
| **Classify / router** | Gemini Flash-Lite | — | NIM nemotron-nano |
| **Coding / build** | DeepSeek V4-Flash | Qwen3-Coder-480B → GLM-5.1 | NIM GLM-5.1 → NIM Qwen3.5-122B → NIM Nemotron-Super |
| **Frontend** | DeepSeek V4-Flash | Qwen3-Coder-480B → GLM-5.1 | NIM GLM-5.1 → NIM Qwen3.5-122B |
| **Reasoning / lead** | DeepSeek V4-Pro | Nemotron-Super | NIM Nemotron-Super → NIM DeepSeek-V4-Pro → NIM MiniMax-M3 |
| **Planning** | DeepSeek V4-Pro | Nemotron-Super | NIM Nemotron-Super → NIM DeepSeek-V4-Pro → NIM MiniMax-M3 |
| **Math** | DeepSeek V4-Pro | Nemotron-Super | NIM Nemotron-Super → NIM DeepSeek-V4-Pro |
| **Review / QA** | GLM-5.1 | DeepSeek V4-Pro → Nemotron-Super | NIM GLM-5.1 → NIM Nemotron-Super |
| **Research / web** | Nemotron-Super | DeepSeek V4-Flash → Gemini Flash | NIM Qwen3.5-122B → NIM GLM-5.1 |
| **Data analysis** | Qwen3-Coder-480B | DeepSeek V4-Flash | NIM Qwen3.5-122B → NIM GLM-5.1 → NIM Nemotron-Super |
| **Vision** | Qwen3-VL | — | NIM Llama-4-Maverick → Gemini Flash |

## Where each model comes from

| Model | Provider (key) | Exact id in `config/models.yaml` |
|---|---|---|
| DeepSeek V4-Flash / V4-Pro | **DeepSeek direct** (`DEEPSEEK_API_KEY`) | `deepseek/deepseek-v4-flash`, `deepseek/deepseek-v4-pro` |
| GLM-5.1 | **DeepInfra** (`DEEPINFRA_API_KEY`) | `deepinfra/zai-org/GLM-5.1` |
| Nemotron-Super | DeepInfra | `deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B` |
| Qwen3-Coder-480B | DeepInfra | `deepinfra/Qwen/Qwen3-Coder-480B-A35B-Instruct-Turbo` |
| Qwen3-VL | DeepInfra | `deepinfra/Qwen/Qwen3-VL-235B-A22B-Instruct` |
| Gemini Flash / Flash-Lite | **Google** (`GEMINI_API_KEY`) | `gemini/gemini-2.5-flash[-lite]` |
| NIM: GLM-5.1, Qwen3.5-122B, Nemotron-Super/Nano, Llama-4-Maverick, MiniMax-M3, DeepSeek-V4-Pro | **NVIDIA NIM free** (`NVIDIA_NIM_API_KEY` ×4 pooled) | `nvidia_nim/...` |

## Notes
- **Two paid keys run the whole paid fleet:** `DEEPSEEK_API_KEY` + `DEEPINFRA_API_KEY`.
  `GEMINI_API_KEY` (router) and `NVIDIA_NIM_API_KEY` (free floor) round it out.
- **DeepSeek is called DIRECT** (not via an aggregator) so its automatic prompt cache stays
  warm — 75–85 % cache-hit on coding loops → near-free builds.
- **GLM 5.1** is the chosen version (live bake-off: cheapest + fewest tokens + verified).
  GLM-5.2 (more defensive, slower) and 4.6 are also catalogued and selectable in the UI.
- **Change any of this in the UI** — Settings → Models → Routing — no code edit; it persists
  to `data/routing.json` (merged over models.yaml, survives deploys).
- **After adding/rotating a key:** `python -m scripts.verify_models` (one cheap probe per
  model; provider catalogs rename models within weeks).

# HANDOFF — read this first

_Last updated: 2026-06-07. Plain-language status of the whole project: what it is, what's
done, what's left, and what needs **your** input. For the deep technical account see
[`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md); the rules + architecture are in
[`CLAUDE.md`](CLAUDE.md); the detailed feature tracker is [`STATUS.md`](STATUS.md)._

---

## 1. What this app is (in one paragraph)

It's a **private, local "AI work assistant"** that runs in your web browser — think of it as
your own Claude Code / ChatGPT, but running on your machine, using whichever AI models you
choose (including **free** ones), and showing you every step it takes. You chat with it; it
plans the work, writes and runs code, builds real documents (Word / Excel / PowerPoint /
PDF), does web research, and saves everything. It **asks your permission before anything
risky**, and it **can never spend more than the dollar limit you set**.

**The one big idea:** anything that might change — which AI models it uses, which specialist
"agents" it has, which tools they can use — lives in simple **config files**, not buried in
code. So you can swap the AI model behind the whole thing by changing one line. That's the
point of the project.

---

## 2. Current status: it works ✅

I verified this today (2026-06-07), not just trusted the docs:

- **The automated test suite passes 60 out of 60** (`scripts/smoke_test.py`) — this checks the
  engine, security gate, memory, the multi-agent loop, and the web server, all offline.
- **Two working AI keys are already set up** in your `.env`: **Google Gemini** and **NVIDIA
  NIM** — both on **free tiers**. So the app can run **at $0 cost** right now.
- **The website front-end is already built** and ready to serve.
- No secrets are hardcoded anywhere in the code (I scanned for it).

**Bottom line: the application is finished and usable for personal/local use.** There is no
half-built feature blocking you. What remains is either *optional power-ups* (which need a
key or a decision from you) or *deployment hardening* you'd only do if you put it on the
public internet.

---

## 3. What's been built (the whole thing, in plain terms)

| Area | What it means for you | Done? |
|---|---|---|
| **The brain (engine)** | Reads your request, decides if it's easy or hard, and routes it to the right helper. Hard jobs get a "lead" agent that makes a to-do list and hands steps to specialists. | ✅ |
| **Swappable AI models** | Change the AI model behind everything by editing one config file or clicking a dropdown. Works with Google, OpenAI, Anthropic, free providers, or local models. | ✅ |
| **Cost control** | Every job has a hard dollar cap and a step cap. Plus an optional daily spending limit. It literally cannot run up a surprise bill. | ✅ |
| **Specialist agents** | A coder, a front-end builder, a researcher, a document writer, an image generator, a QA reviewer — each with only the tools it needs. | ✅ |
| **Safety / permissions** | Risky actions (deleting files, running shell commands) are checked by rules, then by a "security manager" AI, then by **you** clicking Approve/Deny. Everything is logged. | ✅ |
| **Memory** | Remembers the conversation, recalls relevant things from past chats, learns durable facts about you, and can follow rules you approve. | ✅ |
| **Documents** | Produces **real** Word, Excel, PowerPoint, and PDF files (not just text). Verified end-to-end. | ✅ |
| **The website (UI)** | Chat window, a live feed of what the agents are doing, a file/preview panel, approval pop-ups, a memory panel, settings, dark mode, mobile layout. | ✅ |
| **Web research** | Can fetch and read web pages today; full web *search* needs a key (see below). | ✅ / 🟡 |
| **Model Lab** | A "Bench" screen to score and compare different AI models on real tasks before you commit to one. | ✅ |
| **Saving & undo** | Every chat and file is saved. It snapshots your files before each turn so you can rewind. One-command backups. | ✅ |
| **Quality tools** | A test/eval harness and the 60-check smoke test so you can confirm a model swap didn't break anything. | ✅ |

---

## 4. What's left

### A. Nothing is blocking — the app is usable today.

### B. Optional polish (I can do these anytime — **no input needed from you**)
1. **Lock the recent bug-fixes into the test suite** so they can't regress (greeting fast-path,
   empty-response guard, router fallback, document-skill gating).
2. **Make the Docker port configurable** instead of a fixed number, and ship a ready-made
   production settings template.
3. **Add retry-on-rate-limit to the worker loops** so long multi-step jobs recover smoothly
   when a free model briefly rate-limits.
4. **Per-turn live streaming as the default** with a nicer live "typing" lane in the chat.

### C. Needs YOUR input (this is the part you asked about) 👇
| # | What you'd provide | What it unlocks | Required? |
|---|---|---|---|
| 1 | **Push to GitHub:** decide a repo **name** + **public or private**; and since the GitHub CLI isn't installed, either install it or create an empty repo on github.com and give me the link | Gets the code backed up / shareable on GitHub | To push today |
| 2 | A **paid** model key (e.g. OpenAI, Anthropic, or paid Gemini) | Removes the free-tier "5 requests/minute" speed limit so big multi-step jobs run faster | Optional |
| 3 | `SEARCH_API_KEY` in `.env` (Tavily/SerpAPI) | Turns on real web **search** for the research agent (reading pages already works) | Optional |
| 4 | `image_model:` in `config/models.yaml` + its provider key | Turns on AI **image generation** | Optional |
| 5 | `EMBED_MODEL` + its key | Upgrades memory recall from keyword-match to **meaning-based** | Optional |
| 6 | `LANGFUSE_*` keys | Cloud dashboards for tracing (local trace files already work) | Optional |
| 7 | Confirm/choose the **model names** in `config/models.yaml` | Model strings go stale fast; worth a sanity check against your providers | Recommended |

> The full, exhaustive checklist of every optional input lives in
> [`docs/PLACEHOLDERS.md`](docs/PLACEHOLDERS.md).

### D. Only needed if you put this on the public internet (not for personal use)
- Run the shell tool inside a real container sandbox (today it's off-by-default and asks
  permission every time).
- A broader unit-test suite beyond the 60-check smoke test.

### E. Intentionally NOT built (by earlier agreement)
- Multiple user accounts / logins. This is a **single-user, local** app on purpose. (There is
  a single shared access-token option if you ever expose it to your network.)

---

## 5. How to run it

```powershell
# one-time: install Python deps + build the website (already done once on this machine)
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix web install ; npm --prefix web run build

# start it (easiest):
.\run.ps1                  # then open http://localhost:8800
```

**Verify nothing is broken (no cost, no key needed):**
```powershell
.venv\Scripts\python.exe scripts\smoke_test.py     # should say "60 passed, 0 failed"
```

---

## 6. How we'll push to GitHub

The project is **not yet a git repository**, and the **GitHub CLI (`gh`) is not installed**.
So the push is a short, deliberate process — and I've already done the safety prep:

- ✅ Your `.env` (real API keys), your saved chats (`data/`), logs, and build folders are all
  in `.gitignore`, so **none of them will ever be uploaded**.
- ✅ I scanned the code — **no keys are hardcoded** anywhere.
- ✅ I excluded big throwaway build artifacts so the repo stays clean.

**What I still need from you to actually push** (just answer and I'll do the rest):
1. **Repo name** (e.g. `agent-core`).
2. **Public or Private?** (I recommend **Private** for a personal project.)
3. **How to create it** — either:
   - **(a)** you create an empty repo at github.com and paste me the URL, **or**
   - **(b)** you let me install the GitHub CLI (`winget install GitHub.cli`) and sign in, and
     I'll create + push it for you.

Once you tell me those, I'll `git init`, make a clean first commit, and push.

---

## 7. Where to read more
- [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) — the complete technical account (start here for depth).
- [`CLAUDE.md`](CLAUDE.md) — the durable rules + architecture (the things never to break).
- [`STATUS.md`](STATUS.md) — the detailed feature-by-feature tracker + changelog.
- [`docs/PLACEHOLDERS.md`](docs/PLACEHOLDERS.md) — every optional input and what it unlocks.

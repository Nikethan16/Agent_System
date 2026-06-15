# SETUP GUIDE — what to do next, step by step

Plain-language walkthrough for the three things left to switch on, in the order
most people want them:

1. **[Telegram bot](#part-1--control-it-from-your-phone-telegram)** — control the agent from your phone.
2. **[Oracle free server](#part-2--put-it-on-an-always-on-server-oracle-free-vm)** — keep it running 24/7 so the phone bot always answers.
3. **[After that](#part-3--what-to-do-after-that-roadmap)** — the roadmap, easiest wins first.

> Everything below is already **built and tested** — you're just turning features on by
> giving them a key or a home. Nothing here needs new code. The app runs today on your PC
> at **http://localhost:8800**.

---

## Where things stand right now

- The whole system is finished and passes its **158 self-checks**.
- It runs on your computer. When your computer is off or the app is closed, it stops.
- Two things are **coded but switched off**, waiting only on you:
  - **Phone control (Telegram)** — needs a free bot token (5 minutes).
  - **Always-on hosting (Oracle)** — needs a free server (about an hour the first time).

Do them in that order: get the phone bot working on your PC first (quick win), then move
the whole thing to a free server so it's always available.

---

## Part 1 — Control it from your phone (Telegram)

**What you get:** text the agent from anywhere like you'd text a person — "research X",
"write me a doc about Y" — and it replies with the result. When it wants to do something
risky, it asks you, and you reply **/yes** or **/no** right in the chat.

**Why Telegram:** it needs *no website, no public address, no port-opening*. The app
quietly checks Telegram for new messages (this is called "long-polling"), so it works even
from your home PC behind a router. The only requirement is that the app is **running**
(which is exactly why Part 2 — the always-on server — comes next).

### Step 1 — Create the bot

1. Open Telegram (phone or desktop) and search for **@BotFather** (the official one has a
   blue checkmark).
2. Start a chat and send: **/newbot**
3. It asks for a **name** (anything, e.g. "My Agent") and then a **username** that must end
   in `bot` (e.g. `my_agent_core_bot`).
4. It replies with a **token** that looks like `8123456789:AAH...long-random...`. **Copy it.**
   Treat it like a password — anyone with it can message your bot.

### Step 2 — Give the token to the app

On your PC, open the project's **`.env`** file (it's in `C:\Project\agent_system\.env`) in
Notepad and add this line (paste your real token):

```
TELEGRAM_BOT_TOKEN=8123456789:AAH...your-token...
```

Save the file.

### Step 3 — Restart the app and find your chat id

1. Restart the app (stop it and run **`.\run.ps1`** again). On startup it now picks up the
   token and the bot wakes up.
2. In Telegram, open **your new bot** and send it any message (e.g. "hi").
3. The bot replies with a line like:
   *"This bot isn't allowlisted yet. Add this to .env and restart: TELEGRAM_ALLOWED_CHAT_IDS=123456789"*

   That number is **your chat id**. This is a safety feature — until you list your own id,
   the bot refuses to run anything for anyone (so a stranger who guesses your bot can't use it).

### Step 4 — Allow yourself (and set a spend limit)

Back in **`.env`**, add (use the number the bot gave you):

```
TELEGRAM_ALLOWED_CHAT_IDS=123456789
TELEGRAM_MAX_USD=0.5
```

- `TELEGRAM_ALLOWED_CHAT_IDS` — who's allowed to use the bot. Comma-separate to add more
  people, e.g. `123456789,987654321`.
- `TELEGRAM_MAX_USD` — the most one message is allowed to spend (a safety cap; 0.5 = 50¢).

Save and **restart the app one more time.**

### Step 5 — Use it

Now from your phone:

| You send | What happens |
|---|---|
| any task, e.g. *"summarize the latest news on EVs"* | it runs the task and texts back the answer |
| **/new** | starts a fresh conversation (clears the running context) |
| **/help** | shows the quick reference |
| **/yes `<id>`** | approves a risky action it asked about |
| **/no `<id>`** | denies it |

Each phone chat keeps its own memory, just like the web app — so you can carry a
conversation across many messages.

> ⚠️ **The bot only answers while the app is running.** On your PC that means the app must
> be open. To have it answer 24/7, move it to an always-on server — that's Part 2.

---

## Part 2 — Put it on an always-on server (Oracle free VM)

**Goal:** run the app on a small free computer in the cloud that's on all the time, so the
phone bot always answers and you can reach the web UI from anywhere — **privately and
safely**, without exposing anything to the open internet.

**The plan in plain terms:**
1. Get a free Oracle server (a Linux computer in the cloud).
2. Connect to it and install the basics.
3. Copy the project onto it.
4. Set it up and make it start automatically (even after a reboot or crash).
5. Reach its web page privately from your devices using **Tailscale** (a private network).
6. Schedule automatic backups.

This takes about an hour the first time. Take it one step at a time.

### Step A — Create the free Oracle account + server

1. Go to **cloud.oracle.com** and sign up for **Oracle Cloud Free Tier**. It asks for a card
   to verify identity, but the **"Always Free"** resources we use **never charge**.
2. Once in, open the menu (top-left) → **Compute** → **Instances** → **Create instance**.
3. Fill it in:
   - **Name:** `agent-core` (anything).
   - **Image:** click *Edit* → choose **Canonical Ubuntu 24.04**. *(24.04 comes with Python
     3.12, which the app needs — don't pick an older Ubuntu.)*
   - **Shape:** click *Change shape* → **Ampere** → **VM.Standard.A1.Flex** → set **2 OCPUs**
     and **12 GB** memory. *(This ARM shape is free and roomy. If Oracle says "out of
     capacity," try a different "Availability domain" at the top, try again later, or fall
     back to the small free **VM.Standard.E2.1.Micro** — it works too, just tighter.)*
   - **SSH keys:** choose **Save private key** *and* **Save public key** — download **both**
     files and keep the private one safe. This is how you log in.
   - Leave networking on its defaults (a public address is assigned — we only use it for the
     first login; the app itself stays private).
4. Click **Create** and wait until the instance shows **Running**. Note its **public IP
   address** (shown on the instance page).

### Step B — Connect to the server

On your PC, open **PowerShell** and connect (replace the key path and IP):

```powershell
ssh -i C:\path\to\your-private-key.key ubuntu@<PUBLIC-IP>
```

- `ubuntu` is the default username on Ubuntu servers.
- The first time it asks "are you sure?" — type **yes**.
- If Windows complains the key is "too open," run:
  `icacls C:\path\to\your-private-key.key /inheritance:r /grant:r "$($env:USERNAME):R"`

You're now typing commands *on the server*. Everything from here runs there until you type
`exit`.

### Step C — Install the basics

Copy-paste this block (it updates the server and installs git, Python tools, and Node):

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y git python3 python3-venv python3-pip
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
python3 --version   # should say 3.12.x
node --version      # should say v20.x
```

### Step D — Copy the project onto the server

The repo is **private**, so cloning needs a GitHub access token as the "password":

1. On your PC's browser, go to GitHub → **Settings** → **Developer settings** →
   **Personal access tokens** → **Tokens (classic)** → **Generate new token**, tick the
   **`repo`** box, and copy the token.
2. On the server, run:

```bash
cd ~
git clone https://github.com/Nikethan16/Agent_System.git agent_system
# Username: your GitHub username
# Password: paste the token (NOT your GitHub password)
cd agent_system
```

*(Alternative if you'd rather not use a token: zip the project on your PC, then from your PC
run `scp -i your-key.key project.zip ubuntu@<IP>:~/` and unzip it on the server. The git way
is easier to update later.)*

### Step E — Set it up

Still on the server, in the `agent_system` folder:

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
npm --prefix web install
npm --prefix web run build
```

The last line builds the web page the app serves. This takes a few minutes.

### Step F — Create the settings file (`.env`)

Make the settings file with your keys. Run `nano .env` and paste a block like this
(fill in your real values), then press **Ctrl+O**, **Enter**, **Ctrl+X** to save:

```
# at least one model key (copy from your PC's .env)
GEMINI_API_KEY=AIza...
NVIDIA_NIM_API_KEY=nvapi-...

# phone control (same token + your chat id from Part 1)
TELEGRAM_BOT_TOKEN=8123456789:AAH...
TELEGRAM_ALLOWED_CHAT_IDS=123456789
TELEGRAM_MAX_USD=0.5

# REQUIRED on a server: a long random password for the web UI
AGENT_AUTH_TOKEN=paste-a-long-random-string-here

# safety: keep the raw shell tool OFF on a networked machine
AGENT_DISABLE_BASH=1

# optional safety net: stop new runs after $2/day
AGENT_DAILY_USD_CAP=2.0

# optional: smarter memory (recall by meaning) — needs the Gemini key above
EMBED_MODEL=gemini/gemini-embedding-001
```

To generate the random `AGENT_AUTH_TOKEN`, run this and paste its output:
```bash
.venv/bin/python -c "import secrets; print(secrets.token_hex(32))"
```

> Why `AGENT_AUTH_TOKEN` is required here: on a server the app listens beyond your own
> machine, so it demands this password on every web request. Without it, the app refuses
> all non-local connections (a deliberate guard so it can't end up wide open).

**Confirm it's healthy** before going further:
```bash
.venv/bin/python scripts/smoke_test.py    # expect: 158/158 passed
```

### Step G — Make it run automatically (and survive reboots)

We'll register the app as a background service so it starts on boot and restarts if it ever
crashes. Create the service file:

```bash
sudo nano /etc/systemd/system/agentcore.service
```

Paste this exactly (it assumes the project is at `/home/ubuntu/agent_system`):

```ini
[Unit]
Description=AGENT CORE
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/agent_system
ExecStart=/home/ubuntu/agent_system/.venv/bin/uvicorn server.app:app --host 0.0.0.0 --port 8800
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Save (Ctrl+O, Enter, Ctrl+X), then turn it on:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now agentcore
sudo systemctl status agentcore        # should say "active (running)"
```

To watch its live logs any time: `journalctl -u agentcore -f` (Ctrl+C to stop watching).
The app reads `.env` itself, so after you change `.env` just run
`sudo systemctl restart agentcore`.

At this point your **Telegram bot is already live 24/7** — try messaging it. The web page
isn't reachable yet from your devices; that's the next step.

### Step H — Reach the web page privately (Tailscale)

Rather than open the app to the whole internet, we put your devices and the server on a
tiny private network with **Tailscale** (free for personal use). Only your own logged-in
devices can reach it.

1. **On the server:**
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```
   It prints a link — open it in any browser and sign in (Google/Microsoft/GitHub). That
   joins the server to your private network.
2. Get the server's private address:
   ```bash
   tailscale ip -4      # prints something like 100.101.102.103
   ```
3. **On your phone and laptop:** install the **Tailscale** app from the app store and sign
   in with the *same* account.
4. Now open **`http://100.101.102.103:8800`** (use your server's number) on your phone or
   laptop — the app loads. Go to **Settings → Security → Access token** and paste the same
   `AGENT_AUTH_TOKEN` you put in `.env`. Done — full web UI, privately, from anywhere.

> Even tighter (optional): `sudo tailscale serve --bg https / http://127.0.0.1:8800` exposes
> it over an HTTPS address only on your private network. The simple step above is plenty for
> personal use.

### Step I — Automatic backups

Your only un-rebuildable data (chats, memory, files) lives in the `data/` folder. Schedule a
nightly backup:

```bash
crontab -e
```

Add this line at the bottom (runs at 3 AM daily, keeps the last 14 backups):

```
0 3 * * * cd /home/ubuntu/agent_system && /home/ubuntu/agent_system/.venv/bin/python scripts/backup.py --keep 14
```

Backups land in `backups/`. To copy them off the server automatically (recommended), set
`BACKUP_UPLOAD_CMD` in `.env` (see `.env.example` for the rclone example).

### Step J — Final check

- `sudo systemctl status agentcore` → **active (running)**
- Message your Telegram bot → it replies
- Open `http://<tailscale-ip>:8800` on your phone → the UI loads and you can chat

That's it — the system is now always on, controllable from your phone, and reachable
privately from any of your devices.

### Updating it later

When you change the code on your PC and push to GitHub, update the server with:

```bash
cd ~/agent_system
git pull
.venv/bin/pip install -r requirements.txt   # only if dependencies changed
npm --prefix web run build                   # only if the web UI changed
sudo systemctl restart agentcore
```

---

## Part 3 — What to do after that (roadmap)

Ordered easiest-and-highest-value first. None of these are required; the system is complete
without them.

### Quick wins (minutes each)
1. **Add more free NVIDIA keys for speed.** Each free NVIDIA account allows ~40 requests/min.
   Make a few more accounts at build.nvidia.com and add their keys as
   `NVIDIA_NIM_API_KEY_1`, `NVIDIA_NIM_API_KEY_2`, … in `.env`. The app automatically spreads
   work across all of them, so 4 keys ≈ 160 requests/min. (Or add them in the UI under
   **Settings → Fleet & keys**.)
2. **Set a daily spend cap.** Already in the server `.env` above (`AGENT_DAILY_USD_CAP=2.0`).
   Add it on your PC too if you ever use a paid key.
3. **Turn on smarter memory.** Set `EMBED_MODEL=gemini/gemini-embedding-001` (needs the
   Gemini key). It lets the agent recall past chats by *meaning*, not just keywords — and the
   new caching makes repeat lookups free.

### Keep quality honest (do when you swap models)
4. **Run the eval suite** after changing any model: `python -m evals`. It runs real tasks and
   grades pass/fail, so you catch a model swap that quietly got worse.
5. **Use the Model Lab** (Settings → Models → **Model Lab**) to score a new/cheaper model
   before trusting it for real work.
6. **Watch for stale model names.** Provider model strings go dead surprisingly fast (we've
   hit several 404s). If something starts failing, check the **Settings → Model health** panel
   — a model with a high error/fallback count usually means its name retired. Update it in
   `config/models.yaml`.

### Optional bigger features (only if you want them)
These were deliberately deferred as lower-value; the rationale for each is in the **STATUS.md**
changelog. Pick them up only if a real need appears:
- **Real vector index** for memory (faster recall once you have thousands of past chats).
- **Per-project budgets** and an **artifact-export** button in the UI.
- **API rate-limiting + encrypting the stored keys** — worth doing only if you ever expose
  the app more widely than a private Tailscale network.
- **Image generation** — already coded; set an `image_model:` in `config/models.yaml` plus
  the matching provider key to switch it on.

### If you want to do real shell/coding work on the server
The raw shell tool is **off** on the server (`AGENT_DISABLE_BASH=1`) for safety. To turn it
back on *safely*, install Docker and point the app at a container image so every shell
command runs inside a throwaway, network-less sandbox instead of on the real server:

```bash
sudo apt-get install -y docker.io
sudo usermod -aG docker ubuntu      # then log out and back in
```
Then in `.env`: remove `AGENT_DISABLE_BASH=1` and add `AGENT_BASH_DOCKER_IMAGE=python:3.11-slim`,
and `sudo systemctl restart agentcore`.

**To let the verify loop actually run tests (pytest/npm), not just inspect code:**
the sandbox runs with `--network none` (no egress) by default — the right security
posture, but it means the container can't `pip install`/`npm install` at runtime. The
fix is a **preloaded image** with the test tooling baked in, so a suite runs *offline*:

```bash
./docker/build-verify-image.sh        # builds agent-verify:latest (python+node+pytest+common deps)
```
Then in `.env` set `AGENT_BASH_DOCKER_IMAGE=agent-verify:latest` and restart. Need a dep
that isn't baked in? Either add it to `docker/verify.Dockerfile` and rebuild (keeps
`network=none`), or for a one-off set `AGENT_BASH_DOCKER_NETWORK=bridge` to allow a fresh
install for that run (less secure — only when you trust the task).

---

## One-page cheat sheet

| I want to… | Do this |
|---|---|
| Run it on my PC | `.\run.ps1` → http://localhost:8800 |
| Check nothing's broken | `.venv\Scripts\python.exe scripts\smoke_test.py` (expect 158/158) |
| Control it from my phone | Part 1 (BotFather → token → chat id → allowlist) |
| Keep it on 24/7 | Part 2 (Oracle free VM + systemd + Tailscale) |
| Reach the web UI remotely | Tailscale, then `http://<tailscale-ip>:8800` + paste the access token |
| Update the server | `git pull` → rebuild if needed → `sudo systemctl restart agentcore` |
| Back up my data | `python scripts/backup.py --keep 14` (or the nightly cron in Step I) |
| Go faster / cheaper | add `NVIDIA_NIM_API_KEY_1..N` in `.env` or Settings → Fleet & keys |

Full reference for every optional key: **`docs/PLACEHOLDERS.md`**. Current state and history:
**`HANDOFF.md`** and **`STATUS.md`**.

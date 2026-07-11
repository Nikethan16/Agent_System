"""
skill_scan.py — a static security scan for Agent Skills before they can be enabled.

A skill's SKILL.md body is injected into an agent prompt as guidance, and its bundled
scripts may be staged into the workspace and RUN — so a skill pulled from GitHub is
untrusted code + untrusted instructions. This scanner reads a skill's files (no execution,
no network) and flags risky patterns, returning a risk level the Skills Hub uses to GATE
enabling: 'risky' skills can't be enabled without an explicit override.

Deterministic + offline (regex over file text). It is a FIRST-PASS filter, not a proof of
safety — pair it with human review of the SKILL.md (the Hub shows both).
"""
import os
import re

# (pattern, severity, why) — severity: 'high' -> risky, 'medium' -> caution.
# Scripts legitimately do file work, so plain open()/path ops are NOT flagged; we flag
# code execution, shell-out, outbound network, credential/secret access, and path escape.
_RULES = [
    # code execution
    (r"\bexec\s*\(",                 "high",   "dynamic code execution (exec)"),
    (r"\beval\s*\(",                 "high",   "dynamic code execution (eval)"),
    (r"\b__import__\s*\(",           "medium", "dynamic import"),
    (r"\bcompile\s*\(",              "medium", "dynamic compile"),
    (r"\bpickle\.(loads?|Unpickler)","high",   "pickle deserialization (code-exec risk)"),
    # shell / subprocess
    (r"\bsubprocess\b",              "high",   "shell-out via subprocess"),
    (r"\bos\.system\s*\(",           "high",   "shell-out via os.system"),
    (r"\bos\.popen\s*\(",            "high",   "shell-out via os.popen"),
    (r"\bpty\.spawn\b",              "high",   "spawns a shell (pty)"),
    # outbound network
    (r"\b(requests|httpx|aiohttp|urllib|urllib2|socket|http\.client)\b",
                                     "medium", "outbound network access"),
    (r"\bcurl\b|\bwget\b",           "medium", "network fetch via curl/wget"),
    (r"\bftplib\b|\bparamiko\b|\bsmtplib\b", "high", "network exfil channel (ftp/ssh/smtp)"),
    # credential / secret access
    (r"os\.environ|getenv\s*\(",     "medium", "reads environment variables (may access keys)"),
    (r"\.env\b",                     "high",   "references the .env secrets file"),
    (r"(API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)", "medium", "references secret-like names"),
    (r"~/\.ssh|id_rsa|\.aws|\.netrc|credentials", "high", "references credential stores"),
    # path escape / destructive fs
    (r"\.\./\.\.|/etc/|C:\\\\Windows", "high", "path escape / system path access"),
    (r"shutil\.rmtree|rm\s+-rf",     "high",   "recursive delete"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), sev, why) for p, sev, why in _RULES]

# Only scan text files that could carry code/instructions.
_SCAN_EXT = {".py", ".md", ".sh", ".js", ".ts", ".rb", ".pl", ".ps1", ".bat", ".txt",
             ".yaml", ".yml", ".json", ".toml", ""}
_MAX_BYTES = 512_000


def _iter_files(root: str):
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in _SCAN_EXT:
                yield os.path.join(dirpath, fn)


def scan_path(root: str) -> dict:
    """Scan every text file under `root`. Returns {risk, findings:[{file,line,severity,why,
    snippet}], scanned}. risk = 'risky' if any high finding, 'caution' if any medium, else 'safe'."""
    findings = []
    scanned = 0
    if not os.path.isdir(root):
        return {"risk": "safe", "findings": [], "scanned": 0}
    for fp in _iter_files(root):
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(_MAX_BYTES)
        except OSError:
            continue
        scanned += 1
        rel = os.path.relpath(fp, root)
        for i, line in enumerate(text.splitlines(), 1):
            for rx, sev, why in _COMPILED:
                if rx.search(line):
                    findings.append({"file": rel, "line": i, "severity": sev,
                                     "why": why, "snippet": line.strip()[:120]})
                    break        # one finding per line is enough
    # De-dupe by (file, why) so a repeated import isn't 20 rows; keep the first line.
    seen, deduped = set(), []
    for f in findings:
        k = (f["file"], f["why"])
        if k not in seen:
            seen.add(k)
            deduped.append(f)
    risk = ("risky" if any(f["severity"] == "high" for f in deduped)
            else "caution" if deduped else "safe")
    return {"risk": risk, "findings": deduped[:50], "scanned": scanned}


def scan_skill(skill) -> dict:
    """Scan a Skill object (has .path). Bundled skills with no scripts and a benign
    SKILL.md come back 'safe'."""
    return scan_path(getattr(skill, "path", "") or "")

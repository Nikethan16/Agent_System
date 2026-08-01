"""
compress.py — corruption-safe context compression.

Two levers, both SAFE for agentic tool-calling:

1. filter_tool_output(text, cap): when a command's output is too long, keep the HEAD, the
   TAIL, AND the error/warning lines from the dropped middle (deduped) — so a stack trace
   buried in verbose build logs survives, not just the ends. Upgrades a blind head+tail clip.

2. compress_prose(text): shrink natural-language prose with rule-based rewrites — but FIRST
   mask every fragile span (fenced+inline code, markdown links, URLs, file paths, env vars,
   version numbers, CONST_CASE) behind NUL sentinels, rewrite only the prose between them,
   restore the spans verbatim, then VERIFY every fragile span from the ORIGINAL still appears
   in the output. On ANY mismatch — or if the text looks like code/JSON — it returns the
   ORIGINAL unchanged. So it can never corrupt code, JSON, paths, links, or tool arguments.

Pure string logic: provider-agnostic, offline, no model call (safe to live in core/).
"""
import os
import re

# ---------------------------------------------------------------------------
#  Prose compression — mask → rewrite → restore → VERIFY (or fall back)
# ---------------------------------------------------------------------------

# A sentinel that cannot occur in real text (NUL/SOH … STX/NUL) and that none of the prose
# rules below can match. {} is filled with the span's index.
_SENTINEL = "\x00\x01{}\x02\x00"
_SENTINEL_RE = re.compile(r"\x00\x01\d+\x02\x00")

# Fragile spans, masked before any rewrite. Ordered most-specific first. Over-masking is
# SAFE (it just means less compression), so the patterns lean broad on purpose.
_PRESERVE = [
    re.compile(r"```.*?```", re.S),                          # fenced code (backtick)
    re.compile(r"~~~.*?~~~", re.S),                          # fenced code (tilde)
    re.compile(r"`[^`\n]+`"),                                # inline code
    re.compile(r"!?\[[^\]]*\]\([^)]*\)"),                    # markdown links / images
    re.compile(r"(?:https?|ftp)://\S+"),                     # URLs
    re.compile(r"(?:[A-Za-z]:\\|\.{0,2}/)[\w./\\-]+"),       # file paths (win + posix)
    re.compile(r"\$\{?\w+\}?|process\.env\.\w+"),            # env vars
    re.compile(r"\b[vV]?\d+\.\d+(?:\.\d+)+\b"),              # version numbers (1.2.3 / v1.2.3)
    re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b"),       # CONST_CASE identifiers
]

# The subset whose corruption would actually break something — re-checked after rewriting.
_CRITICAL = [
    re.compile(r"```.*?```", re.S),
    re.compile(r"`[^`\n]+`"),
    re.compile(r"!?\[[^\]]*\]\([^)]*\)"),
    re.compile(r"(?:https?|ftp)://\S+"),
]

# Conservative, meaning-preserving rewrites: redundant phrases → shorter (or nothing). No
# single-word filler removal ("just"/"really") — that can shift meaning, and Nikki values
# correctness over a few extra tokens.
_CAVEMAN = [
    (re.compile(r"\bin order to\b", re.I), "to"),
    (re.compile(r"\bdue to the fact that\b", re.I), "because"),
    (re.compile(r"\bin the event that\b", re.I), "if"),
    (re.compile(r"\bat this (?:point in time|moment)\b", re.I), "now"),
    (re.compile(r"\ba (?:large|great) number of\b", re.I), "many"),
    (re.compile(r"\ba number of\b", re.I), "several"),
    (re.compile(r"\bthe majority of\b", re.I), "most"),
    (re.compile(r"\bin spite of the fact that\b", re.I), "although"),
    (re.compile(r"\bwith regard to\b", re.I), "about"),
    (re.compile(r"\bwith respect to\b", re.I), "about"),
    (re.compile(r"\bfor the purpose of\b", re.I), "for"),
    (re.compile(r"\bin the process of\b", re.I), ""),
    (re.compile(r"\bit is important to note that\b", re.I), ""),
    (re.compile(r"\bit should be noted that\b", re.I), ""),
    (re.compile(r"\bplease note that\b", re.I), ""),
    (re.compile(r"\bas a matter of fact\b", re.I), ""),
    (re.compile(r"\bneedless to say\b", re.I), ""),
    (re.compile(r"\bthat being said\b", re.I), ""),
    (re.compile(r"\bprior to\b", re.I), "before"),
    (re.compile(r"\bsubsequent to\b", re.I), "after"),
]
_MULTISPACE = re.compile(r"[ \t]{2,}")
_MULTINEWLINE = re.compile(r"\n{3,}")
_SPACE_BEFORE_PUNCT = re.compile(r" +([,.;:!?])")

_MIN_COMPRESS = int(os.environ.get("AGENT_COMPRESS_MIN_CHARS", "200"))


def mask(text):
    """Replace every fragile span with a sentinel; return (masked_text, restores)."""
    restores = []

    def _sub(m):
        restores.append(m.group(0))
        return _SENTINEL.format(len(restores) - 1)

    out = text
    for pat in _PRESERVE:
        out = pat.sub(_sub, out)
    return out, restores


def unmask(text, restores):
    for i, orig in enumerate(restores):
        text = text.replace(_SENTINEL.format(i), orig)
    return text


def _looks_like_code(text):
    """True when `text` is predominantly code/data (skip prose rewriting entirely)."""
    t = text.strip()
    if not t:
        return True
    if t[0] in "{[<":                                        # JSON / XML / HTML
        return True
    fenced = sum(len(m.group(0)) for m in re.finditer(r"```.*?```", text, re.S))
    if fenced > len(text) * 0.5:                             # mostly a code block
        return True
    symbols = sum(text.count(c) for c in "{};=<>")
    if symbols > len(text) * 0.08:                           # code-ish symbol density
        return True
    return False


def _caveman(text):
    for pat, repl in _CAVEMAN:
        text = pat.sub(repl, text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _MULTISPACE.sub(" ", text)
    text = _MULTINEWLINE.sub("\n\n", text)
    return text


def _validate(original, compressed):
    """Every critical span in the ORIGINAL must survive VERBATIM in `compressed`, and the
    code-fence count must be unchanged. Returns False on any breach (caller keeps original)."""
    for pat in _CRITICAL:
        for m in pat.finditer(original):
            if m.group(0) not in compressed:
                return False
    if original.count("```") != compressed.count("```"):
        return False
    if _SENTINEL_RE.search(compressed):                      # a sentinel leaked (mask/unmask bug)
        return False
    return True


def compress_prose(text):
    """Corruption-safe prose compression. Returns the compressed text, or the ORIGINAL
    unchanged when it looks like code/JSON, is too short, doesn't get smaller, or fails the
    fragile-span verification. Gated by AGENT_COMPRESS_PROSE (default on)."""
    if not text or not isinstance(text, str):
        return text
    if os.environ.get("AGENT_COMPRESS_PROSE", "1").strip().lower() in ("0", "false", "no"):
        return text
    if len(text) < _MIN_COMPRESS or _looks_like_code(text):
        return text
    masked, restores = mask(text)
    out = unmask(_caveman(masked), restores)
    if not _validate(text, out):
        return text                                          # safety net -> original wins
    return out if len(out) < len(text) else text


# ---------------------------------------------------------------------------
#  Smart tool-output filter — head + tail + error lines from the dropped middle
# ---------------------------------------------------------------------------

_TOOL_CAP = int(os.environ.get("AGENT_BASH_OUTPUT_CAP", "4000"))
_MAX_ERR_LINES = int(os.environ.get("AGENT_TOOL_KEEP_ERRLINES", "40"))
_ERR_LINE = re.compile(
    r"(?i)(?:\b(errors?|errno|exception|traceback|fail(?:ed|ure|ing)?|assert(?:ion)?|fatal|"
    r"panic|warn(?:ing)?|cannot|not found|no such|denied|undefined|unexpected|invalid|"
    r"refused|timed?\s?out|missing|E\d{3,}|\d{3}\s+(?:error|forbidden|not))\b"
    r"|[A-Za-z]+(?:Error|Exception|Warning)\b)")               # ValueError / KeyException / …


def filter_tool_output(text, cap=None):
    """Cap `text` to ~`cap` chars while KEEPING the signal: the head, the tail, and any
    error/warning lines from the truncated middle (deduped). For output with too few lines
    to filter meaningfully, falls back to a plain head+tail char clip."""
    cap = cap or _TOOL_CAP
    s = text or ""
    if len(s) <= cap:
        return s
    if s.count("\n") < 4:                                    # too few lines -> char head/tail
        head = cap // 2
        return f"{s[:head]}\n... [{len(s) - cap} chars truncated] ...\n{s[-(cap - head):]}"

    lines = s.split("\n")
    budget = cap // 3
    h, acc = 0, 0
    while h < len(lines) and acc + len(lines[h]) + 1 <= budget:
        acc += len(lines[h]) + 1
        h += 1
    t, acc = len(lines), 0
    while t > h and acc + len(lines[t - 1]) + 1 <= budget:
        acc += len(lines[t - 1]) + 1
        t -= 1

    middle = lines[h:t]
    errs, seen = [], set()
    for ln in middle:
        if _ERR_LINE.search(ln):
            key = ln.strip()
            if key and key not in seen:
                seen.add(key)
                errs.append(ln)

    parts = list(lines[:h])
    dropped = t - h
    if errs:
        parts.append(f"... [{dropped} middle lines truncated · {len(errs)} error/warning line(s) kept] ...")
        parts.extend(errs[:_MAX_ERR_LINES])
    else:
        parts.append(f"... [{dropped} middle lines truncated] ...")
    parts.extend(lines[t:])
    return "\n".join(parts)

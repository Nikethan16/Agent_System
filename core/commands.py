"""
commands.py — user-authored slash-commands (config-dir prompt templates).

A command is a Markdown file in a command dir (default ``config/commands/``, plus any
dir listed in ``AGENT_COMMANDS_DIR``). The filename stem is the command name, so
``config/commands/review.md`` is invoked as ``/review``. An optional YAML frontmatter
block carries metadata; the body is the prompt template.

    ---
    description: Review the current diff
    argument-hint: "[path]"
    ---
    Review @$1 for bugs. Focus: !`git diff --stat`
    Extra notes: $ARGUMENTS

When ``/review src/app.py`` is run, the template is expanded into the real instruction
that goes to the agent:

  * ``$ARGUMENTS``  -> everything the user typed after the command name
  * ``$1``..``$9``  -> individual positional arguments
  * ``@path``       -> the contents of that workspace file (numbered, capped)
  * ``!`cmd```      -> the output of a shell command, run in the SANDBOX (run_bash)

Security: ``@file`` reads and ``!shell`` runs go through the same workspace-confined
tools the agents use (``core/tools``) — invariant #5. Without a configured shell
sandbox, ``!shell`` safely returns the run_bash "no sandbox" notice instead of
touching the host. Argument text is substituted as literal data and is never
re-scanned for ``@``/``!`` tokens, so an argument can't smuggle in a new file read
or shell command.
"""
import os
import re

import yaml

from . import tools

_DIR = os.path.dirname(os.path.abspath(__file__))
_BUILTIN_DIR = os.path.join(_DIR, "..", "config", "commands")

# One combined pass over the template. Order of alternation matters: the shell form
# (``!`...` ``) is matched before a bare ``@file`` so a shell command containing an
# ``@`` isn't mis-read as a file token.
_TOKEN = re.compile(
    r"!`(?P<sh>[^`]*)`"                 # !`shell command`
    r"|@(?P<file>[A-Za-z0-9_./$\-]+)"  # @path/to/file (may contain $1/$ARGUMENTS)
    r"|\$ARGUMENTS"                     # all args
    r"|\$(?P<pos>[1-9])"               # $1..$9
)


def _dirs() -> list:
    """Command dirs, lowest precedence first. Extra dirs from AGENT_COMMANDS_DIR
    (os.pathsep-separated) are loaded AFTER the builtin dir so a user command with
    the same name overrides the shipped one."""
    dirs = [_BUILTIN_DIR]
    extra = os.environ.get("AGENT_COMMANDS_DIR", "").strip()
    if extra:
        dirs.extend(p for p in extra.split(os.pathsep) if p.strip())
    return dirs


def _parse(path: str) -> dict:
    """Parse one command file into {name, description, argument_hint, body}."""
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    meta, body = {}, raw
    if raw.startswith("---"):
        # Split off a leading YAML frontmatter block (--- ... ---).
        end = raw.find("\n---", 3)
        if end != -1:
            try:
                meta = yaml.safe_load(raw[3:end]) or {}
            except Exception:
                meta = {}
            body = raw[end + 4:]
    if not isinstance(meta, dict):
        meta = {}
    name = os.path.splitext(os.path.basename(path))[0].lower()
    return {
        "name": name,
        "description": str(meta.get("description", "") or "").strip(),
        "argument_hint": str(meta.get("argument-hint", meta.get("argument_hint", "")) or "").strip(),
        "body": body.strip("\n"),
    }


def load_commands() -> dict:
    """Every available command as {name: command-dict}. Re-scanned on each call so a
    freshly-added template shows up without a restart (a handful of small files)."""
    out = {}
    for d in _dirs():
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md") or fn.startswith((".", "_")) or fn.lower() == "readme.md":
                continue
            try:
                cmd = _parse(os.path.join(d, fn))
            except Exception:
                continue
            out[cmd["name"]] = cmd   # later dirs override earlier ones
    return out


# Built-in commands handled directly in server/chat.py (not config-dir templates). Listed here
# so the composer "/" menu + ⌘K palette surface them; typing them works regardless.
_BUILTIN_COMMANDS = [
    {"name": "clear", "description": "Forget this chat's earlier turns (start fresh; keeps durable facts)",
     "argument_hint": ""},
    {"name": "compact", "description": "Summarize the conversation so far and free up context (like Claude's /compact)",
     "argument_hint": ""},
]


def list_commands() -> list:
    """Command metadata for the UI (name/description/argument_hint), name-sorted. Includes the
    built-in memory commands plus every config-dir template."""
    cmds = load_commands()
    user = [
        {"name": c["name"], "description": c["description"], "argument_hint": c["argument_hint"]}
        for c in cmds.values()
    ]
    return sorted(_BUILTIN_COMMANDS + user, key=lambda c: c["name"])


def _split(text: str):
    """('/review a b') -> ('review', 'a b', ['a', 'b'])."""
    body = text[1:] if text.startswith("/") else text
    name, _, args = body.partition(" ")
    args = args.strip()
    return name.lower(), args, args.split() if args else []


def is_command(text: str) -> bool:
    """True only when text is ``/name ...`` and ``name`` is a real command — so an
    ordinary message that happens to start with '/' is left untouched."""
    if not text or not text.startswith("/"):
        return False
    name, _, _ = _split(text)
    return bool(name) and name in load_commands()


def _sub_args(s: str, args: str, argv: list) -> str:
    """Substitute $ARGUMENTS / $1..$9 inside a shell command or file path so
    ``!`ls $1``` and ``@$1`` work. Used only on template-authored strings."""
    s = s.replace("$ARGUMENTS", args)
    return re.sub(r"\$([1-9])", lambda m: argv[int(m.group(1)) - 1] if int(m.group(1)) <= len(argv) else "", s)


def expand(text: str, workspace: str, emit=None) -> str:
    """Expand ``/name ...`` into the real instruction. Returns text unchanged if it
    isn't a known command. File reads and shell runs are confined to ``workspace``."""
    if not is_command(text):
        return text
    name, args, argv = _split(text)
    cmd = load_commands().get(name)
    if not cmd:
        return text

    def repl(m: "re.Match") -> str:
        if m.group("sh") is not None:
            command = _sub_args(m.group("sh"), args, argv).strip()
            if not command:
                return ""
            try:
                out = tools.run_bash(command)
            except Exception as e:
                out = f"(command failed: {e})"
            return f"\n```\n$ {command}\n{out}\n```\n"
        if m.group("file") is not None:
            path = _sub_args(m.group("file"), args, argv)
            try:
                content = tools.read_file(path)
            except Exception as e:
                content = f"(could not read {path}: {e})"
            return f"\n=== {path} ===\n{content}\n=== end {path} ===\n"
        if m.group("pos") is not None:
            i = int(m.group("pos"))
            return argv[i - 1] if i <= len(argv) else ""
        return args   # matched literal $ARGUMENTS

    with tools.using_workspace(workspace):
        expanded = _TOKEN.sub(repl, cmd["body"])

    if emit:
        try:
            emit({"type": "command", "name": name, "args": args})
        except Exception:
            pass
    return expanded

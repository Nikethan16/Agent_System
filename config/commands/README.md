# User commands

Markdown prompt templates you invoke as slash-commands in chat. The filename stem is
the command name — `review.md` → `/review`. Drop a `.md` file in here (or in any dir
listed in `AGENT_COMMANDS_DIR`, os.pathsep-separated) and it shows up in the composer's
`/` menu and the ⌘K palette. No restart needed.

## Format

Optional YAML frontmatter, then the prompt body:

```markdown
---
description: One line shown in the picker
argument-hint: "[path]"
---
The prompt the agent receives, with the substitutions below.
```

## Substitutions

| Token          | Expands to                                                        |
|----------------|-------------------------------------------------------------------|
| `$ARGUMENTS`   | everything typed after the command name                           |
| `$1` … `$9`    | individual positional arguments                                   |
| `@path`        | the contents of that workspace file (numbered, size-capped)       |
| `` !`cmd` ``   | the output of `cmd`, run in the **sandbox** (same as `run_bash`)  |

`@file` reads and `!shell` runs are confined to the session workspace, exactly like
the agent's own tools. `!shell` needs a configured shell sandbox
(`AGENT_BASH_DOCKER_IMAGE`); without one it returns the standard "no sandbox" notice
instead of running on the host. Argument text is inserted literally and is never
re-scanned for `@`/`!`, so an argument can't smuggle in a new file read or command.

The shipped `review`, `test`, and `explain` commands are examples — edit or delete them.

---
name: python-project
description: Write clean, correct, tested Python. Use for any Python module, script, function, CLI, or fix where code must actually run and pass tests.
keywords: [python, function, module, script, cli, test, pytest, code, implement, refactor, debug, class, api]
agents: [coder]
---

# Writing production-quality Python

## Standards
- **Runnable & verified**: after writing code, RUN it (or its tests) with `run_bash` and confirm it passes. Never claim success without executing.
- **Tests**: include a quick test. If `pytest` isn't available, add an `assert`-based self-check under `if __name__ == "__main__":` and run `python file.py`.
- **Clear code**: small functions, descriptive names, type hints on public functions, a short docstring each.
- **Edge cases**: handle the obvious ones (empty input, zero/negative, division by zero) and test them.
- **Errors**: raise specific exceptions with clear messages; don't swallow errors silently.
- **Stdlib first**: avoid new dependencies unless necessary; if you add one, note it.

## Process
1. Write the module file(s) to the workspace.
2. Write a matching test (`test_<name>.py` or an inline self-check).
3. **Run it** and read the output. If it fails, fix and re-run until green.
4. Report what you built and the exact command/output that proves it works.

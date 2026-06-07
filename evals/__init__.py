"""
evals — a small eval harness for the agent core (roadmap item #4).

Runs a fixed set of tasks through the REAL pipeline (core.orchestrator.handle_task),
grades each on concrete yes/no criteria, and reports pass-rate + cost. The point is
swap-safety: after changing a model in config/models.yaml, run this to confirm
quality didn't silently degrade.

This package lives OUTSIDE core/ and server/, so it is allowed to import core and
orchestrate runs. It never hardcodes a model name.

NOTE: we set AGENT_WORKSPACE here, BEFORE anything imports core.tools (which fixes
its WORKSPACE constant at import time). This isolates eval file/shell side-effects
in evals/.workspace instead of the project's ./workspace. `setdefault` lets an
explicit user override still win.
"""
import os

os.environ.setdefault(
    "AGENT_WORKSPACE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".workspace"),
)

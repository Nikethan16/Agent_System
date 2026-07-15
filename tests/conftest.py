"""Pytest-wide isolation: point the DB + data dir at a throwaway temp folder BEFORE
any test imports server.db, so the suite never writes into the real ./data/app.db.

Without this, tests that seed rows (e.g. test_project_budget.py creates projects named
'budget-test', 'capped', 'status', 'uncapped') pollute the live dev database and clutter
the sidebar. setdefault() means an explicit APP_DB/DATA_DIR (e.g. in CI) still wins.
"""
import atexit
import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="agentcore_pytest_")
os.environ.setdefault("DATA_DIR", _TMP)
os.environ.setdefault("APP_DB", os.path.join(_TMP, "app.db"))
os.environ.setdefault("AUDIT_LOG", os.path.join(_TMP, "audit.log"))
os.environ.setdefault("AGENT_DISABLE_JANITOR", "1")


@atexit.register
def _cleanup():
    shutil.rmtree(_TMP, ignore_errors=True)

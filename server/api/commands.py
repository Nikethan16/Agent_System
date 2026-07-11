"""commands.py — REST for user-authored slash-commands.

Read-only listing so the composer's `/` menu and the ⌘K palette can surface the
config-dir command templates. The templates themselves are files (see
`config/commands/README.md`); expansion happens server-side in `server/chat.py`.
"""
from fastapi import APIRouter

from core import commands

router = APIRouter(prefix="/api/commands", tags=["commands"])


@router.get("")
def list_commands():
    """Every available command's name / description / argument hint."""
    return {"commands": commands.list_commands()}

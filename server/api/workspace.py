"""workspace.py — read a session's files/artifacts (sandboxed to its workspace)."""
import os
import difflib

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse

from .. import db

router = APIRouter(prefix="/api/sessions", tags=["workspace"])

_TEXT_EXT = {".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml",
             ".yml", ".html", ".css", ".csv", ".sh", ".toml", ".ini", ".xml",
             ".svg", ".mermaid", ".mmd"}
_MAX_READ = 200_000


# Internal/staging dirs that are not user artifacts (hidden from the Files panel).
_HIDDEN_DIRS = {".skills", ".git", "__pycache__", ".venv", "node_modules"}


def _prune(dirs: list):
    """In-place filter for os.walk: drop hidden/internal dirs so they aren't listed."""
    dirs[:] = [d for d in dirs if d not in _HIDDEN_DIRS]


@router.get("/{session_id}/files")
def files(session_id: str):
    root = db.session_workspace(session_id)
    out = []
    for dirpath, _dirs, names in os.walk(root):
        _prune(_dirs)
        for n in sorted(names):
            full = os.path.join(dirpath, n)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            out.append({"path": rel, "size": size,
                        "ext": os.path.splitext(n)[1].lower()})
    return {"root": root, "files": out}


@router.get("/{session_id}/file")
def read_file(session_id: str, path: str = Query(...)):
    root = db.session_workspace(session_id)
    full = os.path.abspath(os.path.join(root, path))
    if not (full == root or full.startswith(root + os.sep)):
        raise HTTPException(400, "path escapes workspace")
    if not os.path.isfile(full):
        raise HTTPException(404, "file not found")
    ext = os.path.splitext(full)[1].lower()
    is_text = ext in _TEXT_EXT
    if not is_text:
        return {"path": path, "ext": ext, "binary": True,
                "note": "binary file (e.g. image) — open via /file/raw"}
    with open(full, encoding="utf-8", errors="replace") as f:
        content = f.read(_MAX_READ)
    return {"path": path, "ext": ext, "binary": False, "content": content}


@router.get("/{session_id}/file/raw")
def file_raw(session_id: str, path: str = Query(...)):
    """Serve a workspace file's RAW bytes with a guessed content-type. The text `/file`
    endpoint feeds the code/markdown viewer; this is what the UI uses to preview binary
    artifacts (generated images, PDFs) and to download any file. Same sandbox guard."""
    root = db.session_workspace(session_id)
    full = os.path.abspath(os.path.join(root, path))
    if not (full == root or full.startswith(root + os.sep)):
        raise HTTPException(400, "path escapes workspace")
    if not os.path.isfile(full):
        raise HTTPException(404, "file not found")
    return FileResponse(full, filename=os.path.basename(full))


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _relfiles(root: str):
    out = []
    for dp, _d, names in os.walk(root):
        _prune(_d)
        for n in names:
            out.append(os.path.relpath(os.path.join(dp, n), root).replace(os.sep, "/"))
    return out


@router.post("/{session_id}/upload")
async def upload(session_id: str, file: UploadFile = File(...)):
    """Save an attached file into the session workspace (under uploads/)."""
    root = db.session_workspace(session_id)
    safe_name = os.path.basename(file.filename or "upload")
    dest_dir = os.path.join(root, "uploads")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, safe_name)
    with open(dest, "wb") as f:
        f.write(await file.read())
    rel = f"uploads/{safe_name}"
    return {"path": rel, "name": safe_name}


def _line_counts(before: str, after: str) -> tuple:
    """(added, removed) line counts between two text blobs, from a unified diff.
    Counts content lines only (skips the +++/--- file headers)."""
    added = removed = 0
    for line in difflib.unified_diff(before.splitlines(), after.splitlines(),
                                     lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def compute_changes(session_id: str) -> list:
    """Files changed since the last checkpoint (the pre-last-turn snapshot), each
    with status + added/removed line counts. Reused by the run_complete event."""
    cp = db.latest_checkpoint_dir(session_id)
    ws = db.session_workspace(session_id)
    out = []
    if not cp:
        return out
    cur, old = set(_relfiles(ws)), set(_relfiles(cp))
    for p in sorted(cur | old):
        before = _read(os.path.join(cp, p)) if p in old else ""
        after = _read(os.path.join(ws, p)) if p in cur else ""
        if p not in old:
            status = "added"
        elif p not in cur:
            status = "deleted"
        elif before != after:
            status = "modified"
        else:
            continue
        added, removed = _line_counts(before, after)
        out.append({"path": p, "status": status, "added": added, "removed": removed})
    return out


@router.get("/{session_id}/changes")
def changes(session_id: str):
    """Files changed since the last checkpoint (the pre-last-turn snapshot)."""
    return {"changes": compute_changes(session_id)}


def _safe_join(root: str, path: str) -> str:
    full = os.path.abspath(os.path.join(root, path))
    if not (full == root or full.startswith(root + os.sep)):
        raise HTTPException(400, "path escapes workspace")
    return full


@router.get("/{session_id}/file/versions")
def file_versions(session_id: str, path: str = Query(...)):
    """Version timeline for a file: the current copy + each checkpoint that held it,
    newest→oldest, collapsing snapshots where the content didn't change. Each entry
    is fetchable via /file/at?checkpoint=<id> (id 'current' = the live workspace)."""
    ws = db.session_workspace(session_id)
    _safe_join(ws, path)  # validate
    entries = [("current", "current (live)", None, _read(os.path.join(ws, path)),
                os.path.isfile(os.path.join(ws, path)))]
    for cp in db.list_checkpoints(session_id):
        cp_path = os.path.join(db._cp_dir(session_id, cp["id"]), path)
        exists = os.path.isfile(cp_path)
        entries.append((cp["id"], cp.get("label") or "checkpoint",
                        cp.get("created_at"), _read(cp_path) if exists else "", exists))

    # Collapse consecutive identical states so the timeline shows real versions only.
    out = []
    prev_content = object()
    for cid, label, created_at, content, exists in entries:
        if exists and content == prev_content:
            continue
        out.append({"checkpoint": cid, "label": str(label)[:80],
                    "created_at": str(created_at) if created_at else None,
                    "exists": exists, "size": len(content) if exists else 0})
        if exists:
            prev_content = content
    return {"path": path, "versions": out}


@router.get("/{session_id}/file/at")
def file_at(session_id: str, path: str = Query(...), checkpoint: str = Query(...)):
    """Read a file's content as it was at a given checkpoint ('current' = live)."""
    ws = db.session_workspace(session_id)
    if checkpoint == "current":
        full = _safe_join(ws, path)
    else:
        cp_root = db._cp_dir(session_id, checkpoint)
        full = _safe_join(cp_root, path)
    ext = os.path.splitext(full)[1].lower()
    if ext not in _TEXT_EXT:
        return {"path": path, "ext": ext, "binary": True, "checkpoint": checkpoint}
    if not os.path.isfile(full):
        raise HTTPException(404, "file not found at that version")
    with open(full, encoding="utf-8", errors="replace") as f:
        return {"path": path, "ext": ext, "binary": False,
                "checkpoint": checkpoint, "content": f.read(_MAX_READ)}


@router.get("/{session_id}/file/diff")
def file_diff(session_id: str, path: str = Query(...)):
    """Unified diff of a file: latest checkpoint (before) vs current (after)."""
    ws = db.session_workspace(session_id)
    full = os.path.abspath(os.path.join(ws, path))
    if not (full == ws or full.startswith(ws + os.sep)):
        raise HTTPException(400, "path escapes workspace")
    cp = db.latest_checkpoint_dir(session_id)
    before = _read(os.path.join(cp, path)) if cp else ""
    after = _read(full)
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="checkpoint", tofile="current",
    ))
    return {"path": path, "changed": before != after, "diff": diff}

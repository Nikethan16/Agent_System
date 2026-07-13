"""
htmlbundle.py — inline an HTML file's LOCAL siblings so a multi-file app previews as
ONE self-contained document.

The artifact preview renders HTML in a sandboxed iframe via srcDoc (a single string),
so an app split across index.html + style.css + script.js shows up unstyled — the iframe
can't fetch the siblings (no base URL, and auth'd sub-requests wouldn't carry the token).
We fix that by inlining: <link rel=stylesheet> -> <style>, <script src> -> inline <script>,
and small <img src> -> data: URIs. Remote/absolute/data URLs are left untouched. Every
referenced path is resolved and guarded to stay INSIDE the workspace (no traversal).
"""
import os
import re
import base64
import mimetypes

_MAX_INLINE_IMG = 3_000_000        # skip inlining images larger than ~3 MB


def _read(root: str, rel: str, binary: bool = False):
    """Read a workspace-relative file, or None if it escapes the workspace / is missing."""
    full = os.path.abspath(os.path.join(root, rel))
    if not (full == root or full.startswith(root + os.sep)) or not os.path.isfile(full):
        return None
    try:
        if binary:
            with open(full, "rb") as f:
                return f.read()
        with open(full, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _is_local(url: str) -> bool:
    """A workspace-relative reference we should inline — not remote/absolute/inline."""
    u = (url or "").strip()
    if not u:
        return False
    return not re.match(r'^(https?:)?//|^data:|^blob:|^#|^mailto:|^/', u, re.I)


def _attr(tag: str, name: str):
    m = re.search(rf'{name}\s*=\s*["\']([^"\']+)["\']', tag, re.I)
    return m.group(1) if m else None


def bundle(root: str, path: str) -> str | None:
    """Return `path` (a workspace HTML file) with its local CSS/JS/images inlined, or
    None if the file doesn't exist. Safe on non-HTML content (returns it unchanged)."""
    html = _read(root, path)
    if html is None:
        return None
    base = os.path.dirname(path)

    def resolve(u: str) -> str:
        return os.path.normpath(os.path.join(base, u.strip())).replace("\\", "/")

    def link_sub(m):
        tag = m.group(0)
        if not re.search(r'rel\s*=\s*["\']?\s*stylesheet', tag, re.I):
            return tag                              # non-stylesheet <link> (icons etc.) — leave
        href = _attr(tag, "href")
        if not href or not _is_local(href):
            return tag
        css = _read(root, resolve(href))
        return f"<style>\n{css}\n</style>" if css is not None else tag

    def script_sub(m):
        tag = m.group(0)
        src = _attr(tag, "src")
        if not src or not _is_local(src):
            return tag
        js = _read(root, resolve(src))
        return f"<script>\n{js}\n</script>" if js is not None else tag

    def img_sub(m):
        tag = m.group(0)
        src = _attr(tag, "src")
        if not src or not _is_local(src):
            return tag
        data = _read(root, resolve(src), binary=True)
        if data is None or len(data) > _MAX_INLINE_IMG:
            return tag
        mime = mimetypes.guess_type(src)[0] or "application/octet-stream"
        return tag.replace(src, f"data:{mime};base64,{base64.b64encode(data).decode()}")

    html = re.sub(r'<link\b[^>]*>', link_sub, html, flags=re.I)
    html = re.sub(r'<script\b[^>]*\bsrc\s*=\s*["\'][^"\']+["\'][^>]*>\s*</script>',
                  script_sub, html, flags=re.I)
    html = re.sub(r'<img\b[^>]*>', img_sub, html, flags=re.I)
    return html

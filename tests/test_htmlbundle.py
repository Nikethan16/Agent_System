"""The HTML bundler inlines a multi-file app's local CSS/JS/images into ONE self-
contained document (so the sandboxed srcDoc preview renders it fully), while leaving
remote/absolute URLs alone and never escaping the workspace."""
import base64

from server import htmlbundle


def _write(root, rel, content, binary=False):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content) if binary else p.write_text(content, encoding="utf-8")


def test_inlines_css_js_and_image(tmp_path):
    _write(tmp_path, "index.html",
           '<!doctype html><html><head>'
           '<link rel="stylesheet" href="style.css">'
           '<link rel="icon" href="favicon.ico">'                 # non-stylesheet link: left alone
           '<link rel="stylesheet" href="https://cdn/x.css">'     # remote: left alone
           '</head><body><img src="logo.png"><script src="script.js"></script></body></html>')
    _write(tmp_path, "style.css", "body{color:red}")
    _write(tmp_path, "script.js", "console.log('hi')")
    _write(tmp_path, "logo.png", b"\x89PNG\r\n\x1a\n" + b"x" * 20, binary=True)

    out = htmlbundle.bundle(str(tmp_path), "index.html")
    assert "<style>\nbody{color:red}\n</style>" in out          # css inlined
    assert "<script>\nconsole.log('hi')\n</script>" in out      # js inlined
    assert 'src="style.css"' not in out                          # original ref gone
    assert 'href="favicon.ico"' in out                           # non-stylesheet link kept
    assert "https://cdn/x.css" in out                            # remote css kept as-is
    assert "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 20).decode() in out


def test_missing_reference_left_untouched(tmp_path):
    _write(tmp_path, "index.html", '<link rel="stylesheet" href="nope.css"><body>hi</body>')
    out = htmlbundle.bundle(str(tmp_path), "index.html")
    assert 'href="nope.css"' in out          # unresolved ref stays (no crash, no blank)


def test_path_traversal_reference_not_inlined(tmp_path):
    (tmp_path.parent / "secret.css").write_text("body{content:'LEAK'}", encoding="utf-8")
    _write(tmp_path, "index.html", '<link rel="stylesheet" href="../secret.css"><body>x</body>')
    out = htmlbundle.bundle(str(tmp_path), "index.html")
    assert "LEAK" not in out                 # escapes workspace -> refused, not inlined


def test_missing_html_returns_none(tmp_path):
    assert htmlbundle.bundle(str(tmp_path), "nope.html") is None

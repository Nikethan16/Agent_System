#!/usr/bin/env python3
"""
check_page.py — headless-browser verification driver (runs INSIDE the verify sandbox).

The agent's `check_page` tool invokes this against a workspace HTML file so the platform can
actually RENDER a UI it built and catch what a text/syntax check never could: a blank screen,
a JavaScript crash, a dead button, a theme that doesn't apply. Loads the page in headless
Chromium (offline, --network none at the container level), collects render + console/page
errors + computed theme, optionally clicks selectors, and prints ONE JSON object to stdout.

Usage (inside the container):  python /opt/check_page.py <html_path> '<opts_json>'
opts: {"expect_text": "...", "click": ["#sel", ...], "timeout_ms": 8000}
"""
import sys
import json


def main() -> None:
    out = {"ok": False, "rendered": False, "console_errors": [], "page_errors": [], "notes": []}
    try:
        path = sys.argv[1]
        opts = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else {}
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"bad args: {e}"}))
        return
    expect_text = (opts.get("expect_text") or "").strip()
    clicks = opts.get("click") or []
    timeout_ms = int(opts.get("timeout_ms", 8000))

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"playwright not available: {e}"}))
        return

    console_errors, page_errors = [], []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage",
                                              "--disable-gpu"])
            page = browser.new_context().new_page()
            page.on("console", lambda m: console_errors.append(m.text[:300])
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: page_errors.append(str(e)[:300]))
            try:
                page.goto("file://" + path, wait_until="load", timeout=timeout_ms)
                page.wait_for_timeout(600)          # let JS init + first render settle
            except Exception as e:
                out["notes"].append(f"navigation issue: {str(e)[:200]}")

            try:
                body_text = (page.inner_text("body") or "").strip()
            except Exception:
                body_text = ""
            out["title"] = (page.title() or "")[:120]
            out["body_text_len"] = len(body_text)
            out["rendered"] = len(body_text) > 20      # a real page has visible text
            try:
                out["body_bg"] = page.eval_on_selector(
                    "body", "el => getComputedStyle(el).backgroundColor")
                out["body_color"] = page.eval_on_selector(
                    "body", "el => getComputedStyle(el).color")
            except Exception:
                pass
            if expect_text:
                out["contains_expect"] = expect_text.lower() in body_text.lower()

            if clicks:
                res = []
                for sel in clicks[:10]:
                    try:
                        page.click(sel, timeout=2500)
                        page.wait_for_timeout(300)
                        res.append({"selector": sel, "clicked": True})
                    except Exception as e:
                        res.append({"selector": sel, "clicked": False, "error": str(e)[:150]})
                out["clicks"] = res

            out["console_errors"] = console_errors[:15]
            out["page_errors"] = page_errors[:15]
            browser.close()
        # Overall pass = it rendered, no JS crashes, and any expected text is present.
        out["ok"] = bool(out["rendered"] and not out["page_errors"]
                         and not out["console_errors"]
                         and (out.get("contains_expect", True)))
    except Exception as e:
        out["error"] = f"check failed: {str(e)[:300]}"
    print(json.dumps(out))


if __name__ == "__main__":
    main()

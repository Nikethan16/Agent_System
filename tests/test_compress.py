"""Tests for corruption-safe compression: the mask/verify prose harness + the smart
tool-output filter. Pure string logic — no models, no network."""
from core import compress


# ---- prose harness --------------------------------------------------------

def test_mask_unmask_roundtrip():
    text = "See `foo()` and visit https://x.com/y and file ./a/b.py and CONST_X_Y here."
    masked, restores = compress.mask(text)
    assert len(restores) >= 4                                  # inline code, url, path, CONST
    assert compress.unmask(masked, restores) == text           # exact round-trip
    assert "`foo()`" not in masked and "https://x.com/y" not in masked


def test_compress_shortens_prose():
    text = ("In order to proceed, it is important to note that a large number of items "
            "were processed prior to the review. ") * 4
    out = compress.compress_prose(text)
    assert len(out) < len(text)
    assert "in order to" not in out.lower()                    # phrase rewritten
    assert "to proceed" in out.lower()                         # meaning preserved


def test_code_urls_and_inline_survive_verbatim():
    block = "```bash\npython -m pytest tests/   # in order to test\n```"
    text = ("In order to run it, it is important to note the steps below:\n"
            f"{block}\n"
            "Then open https://example.com/path/to/deploy and check `config.YAML_KEY` "
            "prior to merge.\n") * 2
    out = compress.compress_prose(text)
    assert block in out                                        # fenced code byte-exact
    assert "https://example.com/path/to/deploy" in out         # URL untouched
    assert "`config.YAML_KEY`" in out                          # inline code untouched
    assert out.count("```") == text.count("```")               # fence count preserved
    assert len(out) < len(text)                                # prose still got compressed
    assert "In order to run" not in out                        # prose phrase rewritten


def test_json_and_code_left_untouched():
    js = '{"a": 1, "in order to": "keep", "b": [1, 2, 3]}\n' * 4
    assert compress.compress_prose(js) == js                   # looks like data -> unchanged


def test_validate_catches_missing_span():
    original = "please see https://a.com/x now"
    assert compress._validate(original, "please see now") is False           # URL dropped
    assert compress._validate(original, "see https://a.com/x later") is True


def test_no_shrink_returns_original():
    text = "The cat sat on the mat and all was well in the little house today. " * 5
    assert compress.compress_prose(text) == text               # no rewrite rule fired


def test_flag_off_is_noop(monkeypatch):
    monkeypatch.setenv("AGENT_COMPRESS_PROSE", "0")
    text = "In order to test, it is important to note that a number of things happened. " * 4
    assert compress.compress_prose(text) == text


def test_short_text_not_compressed():
    assert compress.compress_prose("In order to go.") == "In order to go."   # under min length


# ---- smart tool-output filter --------------------------------------------

def test_filter_keeps_middle_error_lines():
    lines = ["=== build start ==="] + [f"compiling module {i} ok" for i in range(2000)]
    lines[900] = "Traceback (most recent call last):"
    lines[901] = "ValueError: the widget could not be frobnicated"
    lines.append("=== build end (tail) ===")
    text = "\n".join(lines)
    out = compress.filter_tool_output(text, cap=800)
    assert len(out) < len(text)
    assert "build start" in out and "build end (tail)" in out               # head + tail
    assert "Traceback" in out and "the widget could not be frobnicated" in out  # middle errors kept
    assert "middle lines truncated" in out


def test_filter_dedups_repeated_middle_errors():
    head = [f"info {i}" for i in range(300)]
    mid = ["ERROR: disk full"] * 300                           # repeated error, all in the middle
    tail = [f"done {i}" for i in range(300)]
    out = compress.filter_tool_output("\n".join(head + mid + tail), cap=600)
    assert out.count("ERROR: disk full") == 1                  # collapsed to a single kept line


def test_filter_under_cap_unchanged():
    text = "short output\nsecond line\nthird"
    assert compress.filter_tool_output(text, cap=4000) == text


def test_filter_single_huge_line_char_clips():
    text = "x" * 5000                                          # one line, no newlines
    out = compress.filter_tool_output(text, cap=1000)
    assert len(out) < 5000 and "chars truncated" in out

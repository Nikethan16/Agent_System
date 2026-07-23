"""Mic-/typo-tolerant read_file: when the exact path is missing, read the closest real file
(auto for a confident match) or list candidates — so a mis-transcribed 'handoff.in' still reads
HANDOFF.md instead of a bare 'no such file' error."""
import tempfile

from core import tools


def _ws():
    return tempfile.mkdtemp()


def test_fuzzy_reads_stem_match():
    with tools.using_workspace(_ws()):
        tools.write_file("HANDOFF.md", "hello handoff\n")
        r = tools.read_file("handoff.in")                 # mic garble of HANDOFF.md
        assert "hello handoff" in r
        assert "closest match" in r and "HANDOFF.md" in r


def test_case_insensitive_read_works():
    with tools.using_workspace(_ws()):
        tools.write_file("README.md", "readme body\n")
        r = tools.read_file("readme.md")                  # different case
        assert "readme body" in r


def test_ambiguous_lists_candidates():
    with tools.using_workspace(_ws()):
        tools.write_file("HANDOFF.md", "a\n")
        tools.write_file("HANDOFF.txt", "b\n")
        r = tools.read_file("handoff")                    # two equally-good stems
        assert "Did you mean" in r and "HANDOFF.md" in r and "HANDOFF.txt" in r


def test_truly_absent_still_errors():
    with tools.using_workspace(_ws()):
        tools.write_file("HANDOFF.md", "a\n")
        r = tools.read_file("zzzqqq_nope.xyz")
        assert r.startswith("ERROR")


def test_edit_file_suggests_on_missing():
    with tools.using_workspace(_ws()):
        tools.write_file("HANDOFF.md", "a\n")
        r = tools.edit_file("handoff.in", "a", "b")       # never auto-edits the wrong file
        assert r.startswith("ERROR") and "Did you mean" in r and "HANDOFF.md" in r

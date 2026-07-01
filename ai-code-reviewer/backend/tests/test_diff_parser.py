"""Unit tests for the unified diff parser."""
from __future__ import annotations

import pytest

from app.core.diff_parser import DiffHunk, DiffLine, parse_diff

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIMPLE_DIFF = """\
--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,4 @@
 def hello():
+    print("hello")
     pass
-    return None
"""

_TWO_FILE_DIFF = """\
--- a/foo.py
+++ b/foo.py
@@ -1,2 +1,2 @@
-old_foo = 1
+new_foo = 1
--- a/bar.py
+++ b/bar.py
@@ -5,2 +5,3 @@
 existing = True
+added_bar = 2
"""

_TWO_HUNK_DIFF = """\
--- a/multi.py
+++ b/multi.py
@@ -1,3 +1,4 @@
 line1
+added_in_hunk1
 line2
 line3
@@ -10,3 +11,3 @@
 line10
-old_line
+new_line
 line12
"""

_NO_NEWLINE_DIFF = """\
--- a/nonewline.py
+++ b/nonewline.py
@@ -1,1 +1,1 @@
-old line
\\ No newline at end of file
+new line
\\ No newline at end of file
"""


# ---------------------------------------------------------------------------
# parse_diff — empty / degenerate inputs
# ---------------------------------------------------------------------------


def test_parse_diff_empty_string_returns_empty_list():
    assert parse_diff("") == []


def test_parse_diff_no_hunk_header_returns_empty_list():
    diff = "--- a/foo.py\n+++ b/foo.py\n"
    assert parse_diff(diff) == []


def test_parse_diff_lines_before_file_header_are_ignored():
    diff = "diff --git a/foo.py b/foo.py\nindex abc..def 100644\n" + _SIMPLE_DIFF
    hunks = parse_diff(diff)
    assert len(hunks) == 1


# ---------------------------------------------------------------------------
# parse_diff — single-file, single-hunk
# ---------------------------------------------------------------------------


def test_parse_diff_simple_returns_one_hunk():
    hunks = parse_diff(_SIMPLE_DIFF)
    assert len(hunks) == 1


def test_parse_diff_simple_hunk_has_correct_file_path():
    hunks = parse_diff(_SIMPLE_DIFF)
    assert hunks[0].file_path == "foo.py"


def test_parse_diff_simple_hunk_start_line_is_correct():
    hunks = parse_diff(_SIMPLE_DIFF)
    assert hunks[0].start_line == 1


def test_parse_diff_simple_hunk_line_count_is_correct():
    hunks = parse_diff(_SIMPLE_DIFF)
    # context "def hello():", added "print(…)", context "pass", removed "return None"
    assert len(hunks[0].lines) == 4


def test_parse_diff_added_line_has_correct_kind():
    hunks = parse_diff(_SIMPLE_DIFF)
    added = [l for l in hunks[0].lines if l.kind == "added"]
    assert len(added) == 1
    assert added[0].content == '    print("hello")'


def test_parse_diff_removed_line_has_correct_kind():
    hunks = parse_diff(_SIMPLE_DIFF)
    removed = [l for l in hunks[0].lines if l.kind == "removed"]
    assert len(removed) == 1
    assert removed[0].content == "    return None"


def test_parse_diff_context_line_has_correct_kind():
    hunks = parse_diff(_SIMPLE_DIFF)
    context = [l for l in hunks[0].lines if l.kind == "context"]
    assert len(context) == 2


# ---------------------------------------------------------------------------
# parse_diff — line number tracking
# ---------------------------------------------------------------------------


def test_parse_diff_line_numbers_advance_for_added_lines():
    diff = """\
--- a/a.py
+++ b/a.py
@@ -1,1 +1,3 @@
+first_added
+second_added
 context_line
"""
    hunks = parse_diff(diff)
    lines = hunks[0].lines
    assert lines[0].line_number == 1   # first added
    assert lines[1].line_number == 2   # second added
    assert lines[2].line_number == 3   # context


def test_parse_diff_removed_lines_do_not_advance_line_number():
    diff = """\
--- a/a.py
+++ b/a.py
@@ -1,3 +1,2 @@
 context_before
-removed_line
 context_after
"""
    hunks = parse_diff(diff)
    context_before = hunks[0].lines[0]
    removed = hunks[0].lines[1]
    context_after = hunks[0].lines[2]
    # removed line keeps the same line_number as the next new-file line
    assert context_before.line_number == 1
    assert context_after.line_number == 2
    # removed line does not consume a new-file line number
    assert removed.line_number == 2


def test_parse_diff_hunk_start_line_matches_at_header():
    diff = """\
--- a/b.py
+++ b/b.py
@@ -50,3 +50,4 @@
 line50
+added
 line51
 line52
"""
    hunks = parse_diff(diff)
    assert hunks[0].start_line == 50
    assert hunks[0].lines[0].line_number == 50


# ---------------------------------------------------------------------------
# parse_diff — multiple files
# ---------------------------------------------------------------------------


def test_parse_diff_two_files_returns_two_hunks():
    hunks = parse_diff(_TWO_FILE_DIFF)
    assert len(hunks) == 2


def test_parse_diff_two_files_correct_paths():
    hunks = parse_diff(_TWO_FILE_DIFF)
    assert hunks[0].file_path == "foo.py"
    assert hunks[1].file_path == "bar.py"


def test_parse_diff_two_files_independent_line_numbers():
    hunks = parse_diff(_TWO_FILE_DIFF)
    assert hunks[0].start_line == 1
    assert hunks[1].start_line == 5


# ---------------------------------------------------------------------------
# parse_diff — multiple hunks in the same file
# ---------------------------------------------------------------------------


def test_parse_diff_two_hunks_same_file_returns_two_hunks():
    hunks = parse_diff(_TWO_HUNK_DIFF)
    assert len(hunks) == 2


def test_parse_diff_two_hunks_same_file_same_file_path():
    hunks = parse_diff(_TWO_HUNK_DIFF)
    assert hunks[0].file_path == "multi.py"
    assert hunks[1].file_path == "multi.py"


def test_parse_diff_second_hunk_start_line():
    hunks = parse_diff(_TWO_HUNK_DIFF)
    assert hunks[1].start_line == 11


# ---------------------------------------------------------------------------
# parse_diff — "No newline at end of file" markers
# ---------------------------------------------------------------------------


def test_parse_diff_no_newline_marker_is_not_included_as_content_line():
    hunks = parse_diff(_NO_NEWLINE_DIFF)
    assert len(hunks) == 1
    kinds = {l.kind for l in hunks[0].lines}
    contents = [l.content for l in hunks[0].lines]
    # The marker text must not appear as content
    assert all("\\ No newline" not in c for c in contents)


def test_parse_diff_no_newline_marker_does_not_affect_line_count():
    hunks = parse_diff(_NO_NEWLINE_DIFF)
    # Only 1 removed and 1 added line
    assert len(hunks[0].lines) == 2


# ---------------------------------------------------------------------------
# DiffHunk.added_lines property
# ---------------------------------------------------------------------------


def test_diff_hunk_added_lines_returns_only_added():
    hunks = parse_diff(_SIMPLE_DIFF)
    added = hunks[0].added_lines
    assert all(l.kind == "added" for l in added)


def test_diff_hunk_added_lines_empty_when_no_additions():
    diff = """\
--- a/del.py
+++ b/del.py
@@ -1,2 +1,1 @@
 context
-removed
"""
    hunks = parse_diff(diff)
    assert hunks[0].added_lines == []


def test_diff_hunk_added_lines_count_matches_added_in_diff():
    hunks = parse_diff(_TWO_HUNK_DIFF)
    assert len(hunks[0].added_lines) == 1
    assert len(hunks[1].added_lines) == 1


# ---------------------------------------------------------------------------
# DiffLine dataclass
# ---------------------------------------------------------------------------


def test_diff_line_fields_are_set_correctly():
    dl = DiffLine(content="x = 1", line_number=5, kind="added")
    assert dl.content == "x = 1"
    assert dl.line_number == 5
    assert dl.kind == "added"


# ---------------------------------------------------------------------------
# parse_diff — content stripping
# ---------------------------------------------------------------------------


def test_parse_diff_strips_leading_marker_from_content():
    diff = """\
--- a/s.py
+++ b/s.py
@@ -1,1 +1,1 @@
-old content
+new content
"""
    hunks = parse_diff(diff)
    lines = hunks[0].lines
    assert lines[0].content == "old content"
    assert lines[1].content == "new content"


def test_parse_diff_context_line_strips_leading_space():
    diff = """\
--- a/s.py
+++ b/s.py
@@ -1,1 +1,1 @@
 context line here
"""
    hunks = parse_diff(diff)
    assert hunks[0].lines[0].content == "context line here"

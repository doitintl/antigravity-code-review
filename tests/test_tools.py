"""view_file: the byte cap's delivery mechanism, and the workspace boundary."""

import os

import pytest

from antigravity_code_review import tools
from antigravity_code_review.truncation import DEFAULT_CAP_BYTES


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("nested")
    monkeypatch.setenv("AGY_WORKSPACE", str(tmp_path))
    return tmp_path


class TestWorkspaceIsResolvedLate:
    def test_workspace_is_read_at_call_time_not_import_time(self, tmp_path, monkeypatch):
        """A module-level constant captured cwd before any caller could set it.

        On draft#538 that denied every relative path into the real checkout —
        including the files the agent had just been told to go and read.
        """
        (tmp_path / "late.txt").write_text("resolved late")
        monkeypatch.setenv("AGY_WORKSPACE", str(tmp_path))
        assert tools.view_file("late.txt") == "resolved late"


class TestPathResolution:
    def test_absolute_path_inside_the_workspace_is_read(self, workspace):
        assert tools.view_file(str(workspace / "a.txt")) == "hello"

    def test_relative_path_resolves_against_the_workspace(self, workspace):
        """The model does not always honour the AbsolutePath name.

        On a real repository it asked for "CLAUDE.md" and was refused, then
        spent 88 tool calls working around a file it could have read.
        """
        assert tools.view_file("a.txt") == "hello"

    def test_relative_nested_path_resolves(self, workspace):
        assert tools.view_file("sub/b.txt") == "nested"

    def test_relative_path_does_not_resolve_against_the_process_cwd(self, workspace, tmp_path):
        """The guard must not become a way to read the runner's cwd.

        Whether that comes back NOT FOUND or REFUSED is incidental; what matters
        is that the decoy's contents never appear.
        """
        outside = tmp_path.parent / "cwd-decoy.txt"
        outside.write_text("should not be reachable")
        os.chdir(tmp_path.parent)
        assert "should not be reachable" not in tools.view_file("cwd-decoy.txt")


class TestWorkspaceBoundary:
    def test_absolute_path_outside_the_workspace_is_refused(self, workspace, tmp_path):
        outside = tmp_path.parent / "secret.txt"
        outside.write_text("nope")
        assert "REFUSED" in tools.view_file(str(outside))

    def test_traversal_out_of_the_workspace_is_refused(self, workspace):
        assert "REFUSED" in tools.view_file("../../../etc/passwd")

    def test_a_missing_file_says_so(self, workspace):
        assert "NOT FOUND" in tools.view_file("nope.txt")


class TestTruncation:
    def test_an_oversized_file_is_capped_and_says_so(self, workspace):
        (workspace / "big.txt").write_text("x" * (DEFAULT_CAP_BYTES + 10))
        out = tools.view_file("big.txt")
        assert out.startswith("[TRUNCATED:")

    def test_line_range_is_honoured(self, workspace):
        (workspace / "lines.txt").write_text("one\ntwo\nthree\nfour")
        assert tools.view_file("lines.txt", StartLine=2, EndLine=3) == "two\nthree"

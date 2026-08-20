"""Three predicates that each stop a specific, known failure.

None of them need a model. All three are the cheap half of an expensive
mistake: an MCP name that costs a model call to discover, a fork PR that fails
on authentication nobody can interpret, and a stranger spending someone else's
Vertex budget.
"""

import pytest

from antigravity_code_review.guards import (
    ALLOWED_ASSOCIATIONS,
    AllowlistDrift,
    compare_allowlist,
    is_fork,
    may_trigger_rerun,
)

SERVER_TOOLS = [
    "pull_request_read",
    "pull_request_review_write",
    "add_comment_to_pending_review",
    "get_file_contents",
    "list_resources",
    "search_code",
]
CONFIGURED = [
    "pull_request_read",
    "pull_request_review_write",
    "add_comment_to_pending_review",
    "get_file_contents",
    "list_resources",
]


class TestCompareAllowlist:
    def test_subset_of_server_tools_is_clean(self):
        drift = compare_allowlist(CONFIGURED, SERVER_TOOLS)
        assert drift.missing == () and drift.ok

    def test_name_the_server_does_not_have_is_missing(self):
        drift = compare_allowlist([*CONFIGURED, "pull_request_merge"], SERVER_TOOLS)
        assert "pull_request_merge" in drift.missing
        assert not drift.ok

    def test_unused_server_tools_are_reported_but_not_a_failure(self):
        """search_code is deliberately excluded; that is a choice, not drift."""
        drift = compare_allowlist(CONFIGURED, SERVER_TOOLS)
        assert "search_code" in drift.unused
        assert drift.ok

    def test_empty_server_list_fails_loudly(self):
        """A server advertising nothing means the handshake broke."""
        drift = compare_allowlist(CONFIGURED, [])
        assert not drift.ok
        assert len(drift.missing) == len(CONFIGURED)

    def test_exact_match(self):
        drift = compare_allowlist(SERVER_TOOLS, SERVER_TOOLS)
        assert drift.ok and drift.unused == ()

    def test_message_names_what_is_missing(self):
        drift = compare_allowlist(["nope"], SERVER_TOOLS)
        assert "nope" in drift.message


class TestIsFork:
    def test_same_repo_branch_is_not_a_fork(self):
        pr = {"head": {"repo": {"full_name": "o/r"}}, "base": {"repo": {"full_name": "o/r"}}}
        assert is_fork(pr) is False

    def test_different_repo_is_a_fork(self):
        pr = {"head": {"repo": {"full_name": "x/r"}}, "base": {"repo": {"full_name": "o/r"}}}
        assert is_fork(pr) is True

    @pytest.mark.parametrize(
        "pr",
        [
            {},
            {"head": {}, "base": {}},
            {"head": {"repo": None}, "base": {"repo": {"full_name": "o/r"}}},
            {"head": {"repo": {"full_name": "o/r"}}, "base": {"repo": None}},
        ],
    )
    def test_missing_provenance_is_treated_as_a_fork(self, pr):
        """Deleted-fork PRs report repo: null. Refusing to review is cheap."""
        assert is_fork(pr) is True


class TestMayTriggerRerun:
    @pytest.mark.parametrize("assoc", sorted(ALLOWED_ASSOCIATIONS))
    def test_write_access_may_rerun(self, assoc):
        assert may_trigger_rerun(assoc) is True

    @pytest.mark.parametrize(
        "assoc", ["CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "NONE", "MANNEQUIN"]
    )
    def test_everyone_else_may_not(self, assoc):
        assert may_trigger_rerun(assoc) is False

    @pytest.mark.parametrize("assoc", [None, "", "owner", "Member", "SOMETHING_NEW"])
    def test_unknown_or_miscased_defaults_to_refusal(self, assoc):
        """The failure mode is someone else's Vertex bill. Default to no."""
        assert may_trigger_rerun(assoc) is False


class TestAllowlistDriftType:
    def test_ok_is_false_when_missing(self):
        assert AllowlistDrift(missing=("a",), unused=()).ok is False

    def test_ok_is_true_when_only_unused(self):
        assert AllowlistDrift(missing=(), unused=("a",)).ok is True

"""The prompt seed is the one place a file body could leak into the prompt.

These tests exist mostly to make that impossible by accident. The pull-context
strategy is the whole design: metadata and a file list go in the prompt, and the
agent fetches content through a capped tool. A seed that quietly interpolated a
patch would reintroduce the 2.9 MB failure this project was built to avoid,
while still looking correct.
"""

import pytest

from antigravity_code_review.collector import format_file_line, format_seed

PR = {
    "number": 1,
    "title": "Add transfers between accounts",
    "body": "Adds a transfer helper.",
    "base": {"ref": "main"},
    "head": {"ref": "add-transfers"},
}

FILES = [
    {
        "filename": "src/payments/transfers.py",
        "status": "added",
        "additions": 44,
        "deletions": 0,
        "sha": "abc1234",
        "patch": "@@ -0,0 +1,44 @@\n+PAYMENTS_API_KEY = 'sk_live_secret'",
    },
    {
        "filename": "src/payments/rates.generated.json",
        "status": "added",
        "additions": 24001,
        "deletions": 0,
        "sha": "def5678",
    },
]


class TestFormatFileLine:
    def test_carries_the_four_facts(self):
        line = format_file_line(FILES[0])
        assert "src/payments/transfers.py" in line
        assert "added" in line
        assert "+44" in line
        assert "-0" in line
        assert "abc1234" in line

    def test_never_includes_the_patch(self):
        assert "sk_live_secret" not in format_file_line(FILES[0])
        assert "@@" not in format_file_line(FILES[0])

    def test_missing_patch_is_not_an_error(self):
        assert "rates.generated.json" in format_file_line(FILES[1])

    @pytest.mark.parametrize("status", ["added", "modified", "removed", "renamed"])
    def test_all_change_types(self, status):
        f = dict(FILES[0], status=status)
        assert status in format_file_line(f)

    def test_renamed_carries_the_previous_path(self):
        f = dict(FILES[0], status="renamed", previous_filename="src/payments/old.py")
        assert "src/payments/old.py" in format_file_line(f)

    def test_missing_counts_default_to_zero(self):
        f = {"filename": "a.py", "status": "modified", "sha": "aaa"}
        line = format_file_line(f)
        assert "+0" in line and "-0" in line


class TestFormatSeed:
    def test_carries_the_metadata(self):
        seed = format_seed(PR, FILES)
        assert "Add transfers between accounts" in seed
        assert "Adds a transfer helper." in seed
        assert "main" in seed
        assert "add-transfers" in seed

    def test_lists_every_changed_file(self):
        seed = format_seed(PR, FILES)
        assert "src/payments/transfers.py" in seed
        assert "src/payments/rates.generated.json" in seed

    def test_no_patch_reaches_the_seed(self):
        """The invariant the whole pull-context strategy rests on."""
        seed = format_seed(PR, FILES)
        assert "sk_live_secret" not in seed
        assert "@@" not in seed

    def test_empty_file_list_is_stated_not_silent(self):
        seed = format_seed(PR, [])
        assert "no files" in seed.lower() or "0 file" in seed.lower()

    def test_missing_body_does_not_print_none(self):
        seed = format_seed(dict(PR, body=None), FILES)
        assert "None" not in seed

    def test_file_count_is_reported(self):
        assert "2" in format_seed(PR, FILES)

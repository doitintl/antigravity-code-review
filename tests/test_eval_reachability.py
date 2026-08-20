"""A required field is satisfied by the word "yes". That is the hole this closes.

FR2 says a defect must be shown reachable before it counts. `load_fixture`
enforces that the evidence field is present and non-empty, which stops the
field being forgotten and does nothing about the field being filled in with
`TODO`. A fixture that passes the format check and carries no actual evidence is
worse than one that fails it, because it produces a number.

The rules here are deliberately **objective** — a fixed placeholder list and a
length floor. This project has already been burned once by an instrument that
judged text by keyword: a scorer greping for `"page type"` scored a reviewer
that wrote `"pages"` as a miss. A credibility heuristic over prose would be the
same mistake wearing a different hat, so this module does not attempt one.
"""

import pytest

from antigravity_code_review.evalharness.fixtures import Defect, DefectClass, load_fixture
from antigravity_code_review.evalharness.reachability import (
    MIN_EVIDENCE_CHARS,
    UnreachableFixtureError,
    audit,
    evidence_complaint,
    require_reachable,
)

GOOD = (
    "VERIFIED BY EXECUTION 2026-08-20: a transfer of 500 from a balance of 100 returned "
    "True and left the account at -407.50, while the guarded API raises insufficient funds."
)


def _defect(reachable: str, defect_class=DefectClass.LOCAL) -> Defect:
    return Defect(
        id="d1",
        file="src/payments/transfers.py",
        line=33,
        defect_class=defect_class,
        description="writes private state directly, skipping the guard",
        reachable=reachable,
    )


class TestPlaceholdersAreNotEvidence:
    @pytest.mark.parametrize(
        "placeholder",
        ["TODO", "todo", "tbd", "yes", "Yes.", "true", "n/a", "N/A", "unknown", "?", "-", "..."],
    )
    def test_a_placeholder_is_rejected(self, placeholder):
        complaint = evidence_complaint(_defect(placeholder))
        assert complaint is not None
        assert "d1" in complaint

    def test_a_todo_with_trailing_notes_is_still_a_todo(self):
        assert evidence_complaint(_defect("TODO: check this before the run")) is not None

    def test_real_evidence_passes(self):
        assert evidence_complaint(_defect(GOOD)) is None


class TestTheLengthFloor:
    def test_evidence_shorter_than_the_floor_is_rejected(self):
        assert evidence_complaint(_defect("it is reachable")) is not None

    def test_the_complaint_says_what_the_floor_is(self):
        complaint = evidence_complaint(_defect("it is reachable"))
        assert str(MIN_EVIDENCE_CHARS) in complaint

    def test_padding_with_whitespace_does_not_clear_the_floor(self):
        assert evidence_complaint(_defect("reachable" + " " * 200)) is not None

    def test_evidence_at_the_floor_passes(self):
        assert evidence_complaint(_defect("x" * MIN_EVIDENCE_CHARS)) is None


class TestTheComplaintIsUsable:
    def test_it_names_the_defect_and_the_file(self):
        complaint = evidence_complaint(_defect("todo"))
        assert "d1" in complaint and "transfers.py" in complaint

    def test_it_says_what_was_wrong_rather_than_just_that_something_was(self):
        assert "placeholder" in evidence_complaint(_defect("tbd")).lower()


class TestAuditingAWholeSet:
    def _fixture(self, *evidence: str):
        return load_fixture(
            {
                "name": "f",
                "repo": "o/r",
                "base_sha": "1111111",
                "head_sha": "2222222",
                "defects": [
                    {
                        "id": f"d{i}",
                        "file": "a.py",
                        "line": i,
                        "class": "local",
                        "description": "d",
                        "reachable": e,
                    }
                    for i, e in enumerate(evidence)
                ],
            }
        )

    def test_a_clean_set_audits_empty(self):
        assert audit([self._fixture(GOOD, GOOD)]) == []

    def test_every_weak_defect_is_reported_not_just_the_first(self):
        """Fixing them one run at a time is how a set stays weak for a month."""
        complaints = audit([self._fixture("todo", GOOD, "tbd")])
        assert len(complaints) == 2

    def test_complaints_name_their_fixture(self):
        complaints = audit([self._fixture("todo")])
        assert "f" in complaints[0]

    def test_require_reachable_raises_on_a_weak_set(self):
        with pytest.raises(UnreachableFixtureError) as exc:
            require_reachable([self._fixture("todo")])
        assert "d0" in str(exc.value)

    def test_require_reachable_is_silent_on_a_clean_set(self):
        require_reachable([self._fixture(GOOD)])

    def test_the_raise_lists_every_complaint_so_one_pass_fixes_them_all(self):
        with pytest.raises(UnreachableFixtureError) as exc:
            require_reachable([self._fixture("todo", "tbd", GOOD)])
        assert "d0" in str(exc.value) and "d1" in str(exc.value)

"""The fixture format carries this project's claims about *what it measured*.

Every rule here exists because breaking it already produced a wrong number in
`docs/probe-results.md`:

- comparing against a pull request **head** two fix commits after the reviewed
  code measured different source and called it a miss. Hence: SHAs, not a PR
  number;
- a defect shadowed by an earlier `TypeError` was unreachable, and a correct
  triage decision would have scored as a failure. Hence: reachability evidence
  is required before a defect counts;
- a single aggregate recall number would have averaged a 100% band, a 50% band
  and a broken-fixture band into a figure that moves for unattributable
  reasons. Hence: every defect carries a class.
"""

import dataclasses

import pytest

from antigravity_code_review.evalharness.fixtures import (
    Defect,
    DefectClass,
    Fixture,
    FixtureError,
    load_fixture,
    load_fixtures,
)

GOOD_DEFECT = {
    "id": "flag-read-narrower-than-written",
    "file": "src/editor/shell.tsx",
    "line": 214,
    "class": "cross-file",
    "description": "the flag is settable on all seven kinds and read for only two",
    "reachable": "the editor renders the field for every kind; the query filters to two",
}

GOOD_FIXTURE = {
    "name": "example-pr",
    "repo": "acme/widgets",
    "pr": 42,
    "base_sha": "1111111111111111111111111111111111111111",
    "head_sha": "2222222222222222222222222222222222222222",
    "defects": [GOOD_DEFECT],
}


def _fixture(**overrides):
    obj = dict(GOOD_FIXTURE)
    obj.update(overrides)
    return obj


class TestTheHappyPath:
    def test_a_complete_fixture_loads(self):
        f = load_fixture(GOOD_FIXTURE)
        assert isinstance(f, Fixture)
        assert f.repo == "acme/widgets"
        assert f.head_sha.startswith("22222222")
        assert len(f.defects) == 1

    def test_defects_are_typed_records_not_dicts(self):
        d = load_fixture(GOOD_FIXTURE).defects[0]
        assert isinstance(d, Defect)
        assert d.defect_class is DefectClass.CROSS_FILE
        assert d.line == 214

    def test_a_fixture_is_frozen(self):
        """A harness that mutates its own fixture mid-run measured nothing."""
        f = load_fixture(GOOD_FIXTURE)
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.head_sha = "deadbee"  # type: ignore[misc]


class TestPinnedByCommit:
    """FR1. A pull request's head moves; a review of a moved head is a review of
    different code. That error is already in the record."""

    def test_a_pr_number_without_shas_is_rejected(self):
        obj = _fixture()
        del obj["base_sha"]
        del obj["head_sha"]
        with pytest.raises(FixtureError, match="SHA"):
            load_fixture(obj)

    def test_a_missing_head_sha_is_rejected(self):
        obj = _fixture()
        del obj["head_sha"]
        with pytest.raises(FixtureError, match="head_sha"):
            load_fixture(obj)

    def test_a_missing_base_sha_is_rejected(self):
        obj = _fixture()
        del obj["base_sha"]
        with pytest.raises(FixtureError, match="base_sha"):
            load_fixture(obj)

    def test_a_branch_name_is_not_a_sha(self):
        with pytest.raises(FixtureError, match="SHA"):
            load_fixture(_fixture(head_sha="main"))

    def test_a_sha_too_short_to_be_unambiguous_is_rejected(self):
        with pytest.raises(FixtureError, match="SHA"):
            load_fixture(_fixture(head_sha="2222ab"))

    def test_an_abbreviated_sha_of_seven_or_more_is_accepted(self):
        f = load_fixture(_fixture(head_sha="2222abc"))
        assert f.head_sha == "2222abc"

    def test_shas_are_normalised_to_lowercase(self):
        f = load_fixture(_fixture(head_sha="2222ABC"))
        assert f.head_sha == "2222abc"

    def test_the_pr_number_is_optional_metadata_not_the_identifier(self):
        obj = _fixture()
        del obj["pr"]
        assert load_fixture(obj).pr is None


class TestDefectRecords:
    def test_every_defect_needs_a_file(self):
        obj = _fixture(defects=[{**GOOD_DEFECT, "file": ""}])
        with pytest.raises(FixtureError, match="file"):
            load_fixture(obj)

    def test_every_defect_needs_a_description(self):
        d = dict(GOOD_DEFECT)
        del d["description"]
        with pytest.raises(FixtureError, match="description"):
            load_fixture(_fixture(defects=[d]))

    def test_every_defect_needs_a_known_class(self):
        with pytest.raises(FixtureError, match="class"):
            load_fixture(_fixture(defects=[{**GOOD_DEFECT, "class": "vibes"}]))

    def test_all_four_classes_are_accepted(self):
        for name in ("local", "cross-file", "convention", "security"):
            f = load_fixture(_fixture(defects=[{**GOOD_DEFECT, "class": name}]))
            assert f.defects[0].defect_class.value == name

    def test_a_numeric_line_written_as_a_string_is_accepted(self):
        """JSON hand-edited by a human writes "214" as often as 214."""
        f = load_fixture(_fixture(defects=[{**GOOD_DEFECT, "line": "214"}]))
        assert f.defects[0].line == 214

    def test_a_defect_line_may_be_absent(self):
        """Some defects are a property of a file, not of one line."""
        d = dict(GOOD_DEFECT)
        del d["line"]
        assert load_fixture(_fixture(defects=[d])).defects[0].line is None

    def test_a_non_numeric_line_is_rejected_rather_than_coerced(self):
        with pytest.raises(FixtureError, match="line"):
            load_fixture(_fixture(defects=[{**GOOD_DEFECT, "line": "somewhere"}]))

    def test_defect_ids_must_be_unique_within_a_fixture(self):
        with pytest.raises(FixtureError, match="unique"):
            load_fixture(_fixture(defects=[GOOD_DEFECT, dict(GOOD_DEFECT)]))

    def test_a_fixture_with_no_defects_is_rejected(self):
        with pytest.raises(FixtureError, match="defect"):
            load_fixture(_fixture(defects=[]))


class TestReachability:
    """FR2. M1's fixture contained a defect shadowed by an earlier TypeError.
    The reviewer was right not to report dead code, and the harness would have
    scored that correct triage as a miss."""

    def test_a_defect_without_reachability_evidence_is_rejected(self):
        d = dict(GOOD_DEFECT)
        del d["reachable"]
        with pytest.raises(FixtureError, match="reachab"):
            load_fixture(_fixture(defects=[d]))

    def test_empty_reachability_evidence_is_not_evidence(self):
        with pytest.raises(FixtureError, match="reachab"):
            load_fixture(_fixture(defects=[{**GOOD_DEFECT, "reachable": "   "}]))

    def test_the_evidence_is_kept_not_merely_checked(self):
        d = load_fixture(GOOD_FIXTURE).defects[0]
        assert "the query filters to two" in d.reachable


class TestFixtureIdentity:
    def test_a_fixture_needs_a_name(self):
        obj = _fixture()
        del obj["name"]
        with pytest.raises(FixtureError, match="name"):
            load_fixture(obj)

    def test_a_repo_must_be_owner_slash_name(self):
        with pytest.raises(FixtureError, match="repo"):
            load_fixture(_fixture(repo="draft"))

    def test_a_fixture_may_name_a_script_that_executes_its_defects(self):
        """Executed evidence and recorded evidence are not the same claim, so the
        harness has to be able to tell them apart."""
        assert load_fixture(GOOD_FIXTURE).reachability_probe is None
        f = load_fixture(_fixture(reachability_probe="example-reach.py"))
        assert f.reachability_probe == "example-reach.py"

    def test_defects_by_class_groups_for_reporting(self):
        """FR6: recall is reported per class, so the fixture can answer that."""
        f = load_fixture(
            _fixture(
                defects=[
                    GOOD_DEFECT,
                    {**GOOD_DEFECT, "id": "b", "class": "security"},
                    {**GOOD_DEFECT, "id": "c", "class": "security"},
                ]
            )
        )
        assert set(f.defects_by_class()) == {DefectClass.CROSS_FILE, DefectClass.SECURITY}
        assert len(f.defects_by_class()[DefectClass.SECURITY]) == 2


class TestLoadingASet:
    def test_a_directory_of_fixtures_loads_all_of_them(self, tmp_path):
        import json

        (tmp_path / "a.json").write_text(json.dumps(_fixture(name="a")))
        (tmp_path / "b.json").write_text(json.dumps(_fixture(name="b")))
        (tmp_path / "notes.md").write_text("not a fixture")
        names = {f.name for f in load_fixtures(tmp_path)}
        assert names == {"a", "b"}

    def test_a_bad_fixture_names_its_file(self, tmp_path):
        import json

        obj = _fixture()
        del obj["head_sha"]
        (tmp_path / "broken.json").write_text(json.dumps(obj))
        with pytest.raises(FixtureError, match="broken.json"):
            load_fixtures(tmp_path)

    def test_a_file_that_is_not_json_names_itself(self, tmp_path):
        (tmp_path / "truncated.json").write_text('{"name": "a",')
        with pytest.raises(FixtureError, match="truncated.json"):
            load_fixtures(tmp_path)

    def test_duplicate_fixture_names_are_rejected(self, tmp_path):
        import json

        (tmp_path / "a.json").write_text(json.dumps(_fixture(name="same")))
        (tmp_path / "b.json").write_text(json.dumps(_fixture(name="same")))
        with pytest.raises(FixtureError, match="unique"):
            load_fixtures(tmp_path)

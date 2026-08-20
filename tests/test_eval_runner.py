"""The runner is an integration task, so this covers only what is genuinely pure.

Per `workflow.md`, agent configuration and anything whose correctness depends on
how the SDK behaves is verified by a real run rather than by a unit test — "a
unit test here asserts the mock". The runner's real verification is the recorded
run in `docs/probe-results.md`.

What *is* pure, and is here: that the two named configurations actually differ
in the way the comparison depends on. A registry whose entries are secretly
identical would produce two columns of the same measurement and a conclusion
that the judge makes no difference.
"""

from antigravity_code_review.evalharness.runner import (
    CONFIGURATIONS,
    CONTRACT_PASSES_NO_JUDGE,
    CONTRACT_PASSES_WITH_JUDGE,
)


class TestConfigurationsAreActuallyComparable:
    def test_both_configurations_are_registered_under_their_own_names(self):
        assert set(CONFIGURATIONS) == {"contract-passes+judge", "contract-passes-only"}
        assert all(name == cfg.name for name, cfg in CONFIGURATIONS.items())

    def test_they_ask_the_same_questions(self):
        assert CONTRACT_PASSES_WITH_JUDGE.passes == CONTRACT_PASSES_NO_JUDGE.passes

    def test_only_one_of_them_has_a_judge(self):
        assert CONTRACT_PASSES_WITH_JUDGE.judge_instructions is not None
        assert CONTRACT_PASSES_NO_JUDGE.judge_instructions is None

    def test_the_no_judge_arm_asks_its_passes_for_structured_findings(self):
        """The bug this catches, caught once already before it shipped.

        The shipped pass instructions deliberately produce PROSE. A no-judge
        configuration built on them parses zero findings from every run and
        reports a guaranteed 0 — which reads exactly like evidence that the
        judge is essential. An instrument producing the headline number is the
        failure this milestone exists to end."""
        instructions = CONTRACT_PASSES_NO_JUDGE.pass_instructions
        assert "one JSON object per line" in instructions
        assert '"claim"' in instructions

    def test_the_judged_arm_leaves_its_passes_describing_rather_than_reporting(self):
        assert "one JSON object per line" not in CONTRACT_PASSES_WITH_JUDGE.pass_instructions

    def test_the_two_arms_therefore_differ_in_two_things_not_one(self):
        """Recorded rather than hidden. Structured output has to come from
        somewhere, so removing the judge cannot be done alone, and any
        conclusion drawn from this comparison has to say so."""
        assert (
            CONTRACT_PASSES_WITH_JUDGE.pass_instructions
            != CONTRACT_PASSES_NO_JUDGE.pass_instructions
        )

    def test_the_shipped_configuration_runs_the_local_defect_pass_first(self):
        """M2.5: contract questions alone lost a SQL injection and a type
        mismatch. The plain 'is this simply wrong' pass runs first, and a
        configuration that dropped it would measure that regression again."""
        first = CONTRACT_PASSES_WITH_JUDGE.passes[0][0]
        assert "defects in the changed code" == first

    def test_a_configuration_is_frozen(self):
        import dataclasses

        import pytest

        with pytest.raises(dataclasses.FrozenInstanceError):
            CONTRACT_PASSES_WITH_JUDGE.name = "other"  # type: ignore[misc]

"""The configuration carries M0's findings. These tests stop them being undone.

Every assertion here corresponds to something measured rather than assumed. A
future edit that "simplifies" one of them away should fail a test, not quietly
reintroduce a leak.
"""

import pytest
from google.antigravity import types

from antigravity_code_review.config import (
    GITHUB_MCP_IMAGE,
    GITHUB_MCP_TOOLS,
    REVIEW_TOOLS,
    build_config,
)

WRITE_TOOLS = [
    types.BuiltinTools.CREATE_FILE,
    types.BuiltinTools.EDIT_FILE,
    types.BuiltinTools.RUN_COMMAND,
]


@pytest.fixture
def cfg(tmp_path):
    return build_config("p", str(tmp_path), str(tmp_path / "appdata"), "o", "r", 7)


class TestToolSurface:
    @pytest.mark.parametrize("tool", WRITE_TOOLS)
    def test_no_write_tool_is_ever_advertised(self, cfg, tool):
        """Layer 1: the model is never told these exist."""
        assert tool not in cfg.capabilities.enabled_tools

    def test_ask_question_is_absent(self, cfg):
        """An interactive tool in unattended CI stalls waiting for nobody."""
        assert types.BuiltinTools.ASK_QUESTION not in cfg.capabilities.enabled_tools

    def test_context_growth_is_bounded(self, cfg):
        """M1 left this unset; a 30-file PR reached 7.5M cumulative input tokens."""
        assert cfg.capabilities.compaction_threshold is not None

    def test_subagents_disabled(self, cfg):
        """M0: subagent tokens escape BudgetConfig, and delegation fails on Vertex."""
        assert cfg.capabilities.enable_subagents is False

    def test_behaviour_is_autonomous(self, cfg):
        assert cfg.capabilities.agent_behavior == types.AgentBehavior.AUTONOMOUS

    def test_exactly_the_five_review_tools(self, cfg):
        assert set(cfg.capabilities.enabled_tools) == set(REVIEW_TOOLS)


class TestBudget:
    def test_binds_on_input_and_output(self, cfg):
        """The two dials M0 did not observe anything escaping."""
        assert cfg.budget_config.max_input_tokens
        assert cfg.budget_config.max_output_tokens

    def test_does_not_rely_on_max_total_tokens(self, cfg):
        """Evaded by subagent spend (Q4). Relying on it would be a false ceiling."""
        assert cfg.budget_config.max_total_tokens is None

    def test_does_not_rely_on_max_model_calls(self, cfg):
        """Evaded by model-output retries (Q5)."""
        assert cfg.budget_config.max_model_calls is None

    def test_retries_are_tightened(self, cfg):
        """Default is 4 re-prompts at full context; a retried turn cost 7.4x."""
        assert cfg.retry_config.model_output_retry.max_retries == 1


class TestModelPinning:
    def test_model_is_pinned_so_the_rate_is_knowable(self, cfg):
        """The rate table keys on the model. Unpinned means unpriceable."""
        from antigravity_code_review.rates import FLASH, RATES
        assert cfg.model == FLASH
        assert FLASH in RATES

    def test_thinking_level_is_still_unset(self, cfg):
        """A separate axis from the model, and M5's to measure."""
        assert getattr(cfg, "model_options", None) is None


class TestIsolation:
    def test_relative_app_data_dir_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="absolute"):
            build_config("p", str(tmp_path), "relative/path")

    def test_home_relative_app_data_dir_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="absolute"):
            build_config("p", str(tmp_path), "~/scratch")

    def test_workspace_is_set_so_workspace_only_applies(self, cfg, tmp_path):
        assert cfg.workspaces == [str(tmp_path)]

    def test_env_is_minimal(self, cfg):
        """The MCP container is a child of the harness and inherits this."""
        assert set(cfg.env) <= {"GITHUB_PERSONAL_ACCESS_TOKEN", "PATH", "HOME"}


class TestMcpServer:
    def test_container_is_pinned_by_tag(self, cfg):
        assert ":" in GITHUB_MCP_IMAGE and not GITHUB_MCP_IMAGE.endswith(":latest")

    def test_search_code_is_excluded(self):
        assert "search_code" not in GITHUB_MCP_TOOLS

    def test_list_resources_is_not_configured(self):
        """The server does not offer it; it is an MCP protocol method, not a tool.

        Verified against the real server's tools/list, which advertises 40 tools
        and no list_resources. Configuring it failed the preflight every run.
        """
        assert "list_resources" not in GITHUB_MCP_TOOLS

    def test_allowlist_appears_in_both_layers(self, cfg):
        server = cfg.mcp_servers[0]
        assert set(server.enabled_tools) == set(GITHUB_MCP_TOOLS)


class TestSystemInstructions:
    def test_states_pr_content_is_untrusted(self, cfg):
        assert "UNTRUSTED" in cfg.system_instructions

    def test_carries_exact_mcp_casing(self, cfg):
        assert "pullNumber" in cfg.system_instructions
        assert "subjectType: LINE" in cfg.system_instructions

    def test_names_the_repository_so_calls_do_not_resolve_to_slash(self, cfg):
        """A CI run failed with "Could not resolve to a Repository with the name '/'"."""
        assert "owner:      o" in cfg.system_instructions
        assert "repo:       r" in cfg.system_instructions
        assert "pullNumber: 7" in cfg.system_instructions

    def test_spells_out_the_posting_sequence(self, cfg):
        """The agent invented a tool name when left to guess the sequence."""
        assert "pull_request_review_write" in cfg.system_instructions
        assert "add_comment_to_pending_review" in cfg.system_instructions

    def test_directs_the_agent_to_the_diff_first(self, cfg):
        """Opening whole files to find changes is what broke draft#538."""
        i = cfg.system_instructions.index("view_diff")
        j = cfg.system_instructions.index("view_file")
        assert i < j, "view_diff must be introduced before view_file"

    def test_requires_every_tool_call_to_have_a_purpose(self, cfg):
        """87 tool calls, zero findings, on the first real pull request.

        Note this is deliberately NOT "do not explore" any more. A blanket ban
        on exploring also bans following a reference out of the diff, which is
        where the findings worth having actually live.
        """
        text = cfg.system_instructions
        assert "CLEAR PURPOSE" in text.upper()
        assert "at random" in text.lower()
        assert "do not explore" not in text.lower()

    def test_carries_an_explicit_do_not_flag_list(self, cfg):
        text = cfg.system_instructions.lower()
        assert "what not to flag" in text
        for suppressed in ("pre-existing", "linter", "style", "generated files"):
            assert suppressed in text

    def test_sets_a_precision_bar(self, cfg):
        assert "NOT CERTAIN" in cfg.system_instructions.upper()
        assert "false positive" in cfg.system_instructions.lower()

    def test_tells_the_agent_not_to_submit(self, cfg):
        assert "runner submits" in cfg.system_instructions.lower()


class TestCrossFileReasoning:
    """The findings that matter live where changed code meets unchanged code."""

    def test_directs_the_agent_to_follow_references(self, cfg):
        text = cfg.system_instructions.lower()
        assert "follow the references out of the diff" in text

    def test_says_where_the_valuable_findings_are(self, cfg):
        """Diff-only review finds what a linter finds."""
        assert "linter would have caught" in cfg.system_instructions.lower()

    def test_permits_checking_before_dismissing(self, cfg):
        assert "good use of a tool call" in cfg.system_instructions.lower()


class TestContractPasses:
    """Contract questions add cross-file recall; they must not remove local recall."""

    def test_a_local_defect_pass_runs_first(self):
        from antigravity_code_review.config import CONTRACT_PASSES
        assert CONTRACT_PASSES[0][0] == "defects in the changed code"

    def test_the_local_pass_asks_about_security(self):
        from antigravity_code_review.config import CONTRACT_PASSES
        q = CONTRACT_PASSES[0][1].lower()
        for topic in ("security", "credential", "query", "swallowed"):
            assert topic in q

    def test_the_local_pass_forbids_reframing_a_credential(self):
        """The asymmetry lens called a committed API key 'unused configuration'."""
        from antigravity_code_review.config import CONTRACT_PASSES
        assert "do not describe it as unused configuration" in CONTRACT_PASSES[0][1]

    def test_the_contract_questions_survive(self):
        from antigravity_code_review.config import CONTRACT_PASSES
        names = [n for n, _ in CONTRACT_PASSES]
        assert "write/read asymmetry" in names
        assert "identifier uniqueness" in names
        assert "side-effect frequency" in names

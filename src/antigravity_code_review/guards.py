"""Cheap checks that each prevent one specific, known-expensive failure.

None of these need a model, which is the point. Every one of them replaces a
failure that would otherwise be discovered at the price of a model call, a
confusing CI error, or somebody else's Vertex bill.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# GitHub's author_association values that imply write access to the repository.
# Anything outside this set cannot trigger a billed re-run.
ALLOWED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


@dataclass(frozen=True)
class AllowlistDrift:
    """The difference between what we asked for and what the server offers."""

    missing: tuple[str, ...]
    unused: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Unused server tools are a deliberate choice; missing ones are a bug."""
        return not self.missing

    @property
    def message(self) -> str:
        parts = []
        if self.missing:
            parts.append(f"configured but not offered by the server: {', '.join(self.missing)}")
        if self.unused:
            parts.append(f"offered but not enabled (deliberate): {', '.join(self.unused)}")
        return "; ".join(parts) or "allowlist matches the server exactly"


def compare_allowlist(configured: Iterable[str], server_tools: Iterable[str]) -> AllowlistDrift:
    """Compare the configured MCP tool names against what the server advertises.

    M0 recorded that the SDK exposes names the server does not have, and that
    discovering one through a failed call costs a model call. Running this
    before the first turn converts that into a startup error costing nothing.
    """
    configured_set = list(dict.fromkeys(configured))
    server_set = set(server_tools)
    missing = tuple(name for name in configured_set if name not in server_set)
    unused = tuple(sorted(server_set - set(configured_set)))
    return AllowlistDrift(missing=missing, unused=unused)


def is_fork(pr: dict[str, Any]) -> bool:
    """True when the pull request head lives in a different repository.

    A fork PR gets a read-only token and no identity federation, so the reviewer
    cannot reach Vertex at all. Detecting it lets the job say that plainly
    instead of dying on an authentication error nobody can interpret.

    Missing provenance counts as a fork. A PR whose head repository was deleted
    reports `repo: null`, and refusing to review is cheap next to handing a
    federated credential to an unknown head.
    """
    head = (pr.get("head") or {}).get("repo") or {}
    base = (pr.get("base") or {}).get("repo") or {}
    head_name = head.get("full_name")
    base_name = base.get("full_name")
    if not head_name or not base_name:
        return True
    return head_name != base_name


def may_trigger_rerun(author_association: str | None) -> bool:
    """Whether this commenter may spend a billed review run.

    Defaults to refusal on anything unrecognised. A per-run budget bounds the
    cost of one run; it does nothing about the number of runs, so an open
    trigger on a public repository is an invitation to drain the project.
    """
    if not author_association:
        return False
    return author_association in ALLOWED_ASSOCIATIONS

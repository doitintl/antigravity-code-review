"""Custom tools for the reviewer.

Currently one: a `view_file` that caps what it returns.

The built-in `view_file` has no configurable byte limit, and `design.md`
establishes that no `BudgetConfig` dial refuses a single oversized prompt — they
are all session totals. So the cap has to live in the tool itself, and the SDK's
documented way to do that is to register a custom tool with the **exact same
name**, which the harness then prioritises over the built-in.

The parameter contract is `AbsolutePath` / `StartLine` / `EndLine`, captured
from a real call against `0.1.12` (Q6) rather than guessed. Matching it exactly
matters: the model has been trained on the built-in's shape, and a divergent
signature would cost a retry on every call.
"""

from __future__ import annotations

import os

from antigravity_code_review.truncation import DEFAULT_CAP_BYTES, truncate


def _workspace() -> str:
    """Resolve the workspace at call time, not at import time.

    A module-level constant captured `os.getcwd()` when the module was first
    imported, which is before any caller has had a chance to set AGY_WORKSPACE.
    The result was a guard that denied every relative path into the real
    workspace — including, on draft#538, the exact files the agent had just been
    instructed to go and read.

    Bound so a path traversal cannot escape the checkout. policy.workspace_only()
    also covers this; belt and braces, because this tool replaces the built-in
    that policy was written against.
    """
    return os.environ.get("AGY_WORKSPACE") or os.getcwd()


def view_file(AbsolutePath: str, StartLine: int | None = None, EndLine: int | None = None) -> str:
    """View the contents of a file, optionally a line range.

    Args:
      AbsolutePath: Absolute path of the file to read.
      StartLine: Optional 1-based first line to return.
      EndLine: Optional 1-based last line to return.

    Returns:
      The file contents, truncated with a visible marker if oversized.
    """
    # Resolve relative paths against the WORKSPACE, not the process cwd.
    #
    # The parameter is named AbsolutePath and the model mostly honours that, but
    # not always: on a real repository it asked for "CLAUDE.md" and the guard
    # refused, because realpath() resolved it against wherever the runner
    # happened to be. The agent then spent 88 tool calls and $1.51 working
    # around a file it had every right to read.
    #
    # Refusing a path outside the workspace is correct. Refusing a *relative*
    # path that names a file inside it is just a bug wearing a security costume.
    workspace = os.path.realpath(_workspace())
    candidate = AbsolutePath if os.path.isabs(AbsolutePath) else os.path.join(workspace, AbsolutePath)
    resolved = os.path.realpath(candidate)
    if not resolved.startswith(workspace + os.sep) and resolved != workspace:
        return f"[REFUSED: '{AbsolutePath}' is outside the workspace and was not read.]"

    if not os.path.isfile(resolved):
        return f"[NOT FOUND: '{AbsolutePath}' does not exist or is not a file.]"

    try:
        with open(resolved, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError as exc:
        return f"[UNREADABLE: '{AbsolutePath}': {exc}]"

    if StartLine is not None or EndLine is not None:
        lines = text.splitlines()
        start = max((StartLine or 1) - 1, 0)
        end = EndLine if EndLine is not None else len(lines)
        text = "\n".join(lines[start:end])

    return truncate(text, AbsolutePath, cap_bytes=DEFAULT_CAP_BYTES)


def make_view_diff(patches: dict[str, str], cap_bytes: int = DEFAULT_CAP_BYTES):
    """Build a `view_diff` tool serving the hunks already fetched by the collector.

    This is the tool the reviewer was missing. On `doitbse/draft#538` the agent
    opened `docs/openapi.json` — 2,947,014 bytes, 74,560 lines — to review a
    30-line change at line 13,329. The byte cap gave it the first 3,113 lines, so
    it read the wrong region entirely and could not have reviewed that file.

    The patch for the same change is **2,799 bytes**: a thousandth of the file,
    and unlike the file, it contains the change.

    `design.md` is right that hunks must not go in the prompt seed — attaching
    them for every file is what produced the original 1M-token failure. Serving
    them through a tool is the same pull-context principle the seed already
    follows, applied to the thing actually under review.

    No API call: `list_changed_files` already fetches the patches and the
    collector discards them.
    """

    def view_diff(FilePath: str) -> str:
        """View the changed lines (diff hunks) for one file in this pull request.

        Prefer this over view_file. It shows exactly what the pull request
        changed, is far smaller than the file, and needs no line numbers.

        Args:
          FilePath: Path of the changed file, as given in the changed-file list.

        Returns:
          The unified diff hunks for that file.
        """
        patch = patches.get(FilePath)
        if patch is None:
            known = ", ".join(sorted(patches)[:8])
            return (
                f"[NO DIFF: '{FilePath}' is not a changed file in this pull request, "
                f"or GitHub omitted its patch because the diff is too large. "
                f"Changed files include: {known}]"
            )
        return truncate(patch, f"{FilePath} (diff)", cap_bytes=cap_bytes)

    return view_diff

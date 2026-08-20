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

# Bound the workspace so a path traversal cannot read outside the checkout.
# policy.workspace_only() also covers this; belt and braces, because this tool
# replaces the built-in that policy was written against.
_WORKSPACE = os.environ.get("AGY_WORKSPACE") or os.getcwd()


def view_file(AbsolutePath: str, StartLine: int | None = None, EndLine: int | None = None) -> str:
    """View the contents of a file, optionally a line range.

    Args:
      AbsolutePath: Absolute path of the file to read.
      StartLine: Optional 1-based first line to return.
      EndLine: Optional 1-based last line to return.

    Returns:
      The file contents, truncated with a visible marker if oversized.
    """
    resolved = os.path.realpath(AbsolutePath)
    workspace = os.path.realpath(_WORKSPACE)
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

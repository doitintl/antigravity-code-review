"""Cap file reads by size, and say so loudly when we do.

Two rules, both from `design.md`, both learned the hard way:

**Cap by size, never by filename.** The obvious alternative is a denylist —
`package-lock.json`, `*.lock`, and so on. Denylists only cover the generated
files someone already imagined, and every repository has a different one: a
snapshot, a bundled schema, a fixture, a vendored client. A byte cap covers the
ones nobody has invented yet.

**Truncation must be loud.** A silently shortened file is worse than an absent
one, because the model reasons confidently about content it cannot see and the
reader of the review cannot tell that it did.
"""

from __future__ import annotations

# 128 KiB. Large enough for essentially any hand-written source file, small
# enough that a generated artefact cannot crowd out the review.
DEFAULT_CAP_BYTES = 131_072


def truncate(text: str, path: str, cap_bytes: int = DEFAULT_CAP_BYTES) -> str:
    """Return `text` capped to `cap_bytes`, with a loud marker if it was cut.

    The cap is measured in **bytes**, not characters, because that is what
    actually bounds the prompt. Multi-byte characters are never split: the cut
    falls back to the last complete character, so the model is never handed
    invalid UTF-8.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= cap_bytes:
        return text

    # errors="ignore" drops a trailing partial character rather than raising.
    head = encoded[:cap_bytes].decode("utf-8", errors="ignore")

    marker = (
        f"\n\n[TRUNCATED: '{path}' is {len(encoded):,} bytes, "
        f"showing the first {cap_bytes:,}. "
        f"{len(encoded) - cap_bytes:,} bytes were not read. "
        f"Do not draw conclusions about the part you cannot see.]"
    )
    return head + marker

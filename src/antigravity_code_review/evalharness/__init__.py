"""The evaluation harness — what makes a claim about review quality checkable.

Named `evalharness` rather than `eval` because `eval` is a builtin, and a module
that shadows it inside a package is a trap laid for whoever reads it next.

Every rule enforced in here traces to a wrong number already published in
`docs/probe-results.md`. The harness exists to stop repeating those, and a
harness that repeats them is worse than none: its numbers carry authority.
"""

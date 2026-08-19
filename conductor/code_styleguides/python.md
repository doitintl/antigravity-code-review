# Google Python Style Guide Summary

This document summarizes key rules and best practices from the Google Python
Style Guide.

## 1. Python Language Rules

-   **Linting:** Run `pylint` on your code to catch bugs and style issues.
-   **Imports:** Use `import x` for packages/modules. Use `from x import y` only
    when `y` is a submodule.
-   **Exceptions:** Use built-in exception classes. Do not use bare `except:`
    clauses.
-   **Global State:** Avoid mutable global state. Module-level constants are
    okay and should be `ALL_CAPS_WITH_UNDERSCORES`.
-   **Comprehensions:** Use for simple cases. Avoid for complex logic where a
    full loop is more readable.
-   **Default Argument Values:** Do not use mutable objects (like `[]` or `{}`)
    as default values.
-   **True/False Evaluations:** Use implicit false (e.g., `if not my_list:`).
    Use `if foo is None:` to check for `None`.
-   **Type Annotations:** Strongly encouraged for all public APIs.

## 2. Python Style Rules

-   **Line Length:** Maximum 80 characters.
-   **Indentation:** 4 spaces per indentation level. Never use tabs.
-   **Blank Lines:** Two blank lines between top-level definitions (classes,
    functions). One blank line between method definitions.
-   **Whitespace:** Avoid extraneous whitespace. Surround binary operators with
    single spaces.
-   **Docstrings:** Use `"""triple double quotes"""`. Every public module,
    function, class, and method must have a docstring.
    -   **Format:** Start with a one-line summary. Include `Args:`, `Returns:`,
        and `Raises:` sections.
-   **Strings:** Use f-strings for formatting. Be consistent with single (`'`)
    or double (`"`) quotes.
-   **`TODO` Comments:** Use `TODO(username): Fix this.` format.
-   **Imports Formatting:** Imports should be on separate lines and grouped:
    standard library, third-party, and your own application's imports.

## 3. Naming

-   **General:** `snake_case` for modules, functions, methods, and variables.
-   **Classes:** `PascalCase`.
-   **Constants:** `ALL_CAPS_WITH_UNDERSCORES`.
-   **Internal Use:** Use a single leading underscore (`_internal_variable`) for
    internal module/class members.

## 4. Main

-   All executable files should have a `main()` function that contains the main
    logic, called from a `if __name__ == '__main__':` block.

**BE CONSISTENT.** When editing code, match the existing style.

*Source:
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)*

---

# Project conventions — antigravity-code-review

These are additions specific to this project, appended to the standard guide. They exist because each one has already been the source of a real error here.

## Pin, and say what you pinned against

**Pin the SDK exactly** (`google-antigravity==0.1.12`), never a range. It is a 0.1.x package shipping a compiled runtime binary; behaviour has changed between the documentation and the wheel already.

**Any comment asserting SDK behaviour names the version it was checked against.** `# verified 0.1.12: all BudgetConfig dials are session-cumulative` is useful. `# budget is cumulative` rots silently.

## Evidence rules for anything that becomes a number

**Every rate carries a source URL and a verification date**, in the code, next to the value. A rate without one is a defect however correct it happens to be — a reader cannot distinguish a checked figure from a plausible guess.

**Never emit `0.0` as a cost for a run that spent tokens.** A failed or zero-token run records `None` with a reason. Under-reporting is the failure mode that hurts exactly when someone is investigating a spike.

**Unknown model or unknown service tier reports tokens and no cost.** Never borrow a neighbouring rate. A missing number is obvious; a wrong one is invisible and gets quoted in meetings.

## Marking what is not known

**Unverified SDK behaviour is marked unverified at the call site**, not only in the docs:

```python
# UNVERIFIED (0.1.12): whether retries count against max_model_calls.
# If they do, the ceiling is tighter than budget_for() assumes.
```

Silence reads as confidence. If it has not been checked, the code says so where the assumption is being made.

## Tool and parameter names

**Use the `BuiltinTools` enum, never a bare string.** It subclasses `str`, so it works everywhere a string does and fails at import rather than at runtime. `LIST_DIR` is `list_directory` and `SEARCH_DIR` is `search_directory` — the hand-written strings are the error-prone half.

**MCP tool names are validated against the server's `tools/list` at startup.** `enabled_tools` is an exposure filter, not a validator: a wrong name reaches the model and fails at call time, costing a model call.

**Built-in tool arguments are PascalCase** (`AbsolutePath`, `StartLine`, `EndLine`). Verified from live calls, not from the documentation, which gets this wrong.

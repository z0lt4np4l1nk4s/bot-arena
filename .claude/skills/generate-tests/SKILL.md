---
name: generate-tests
description: Write unittest tests and doctests for Bot Arena following the project's TDD rules. Use when starting a new behaviour (write the failing tests first), when asked to generate, add or improve tests for a module, or when the reviewer found missing tests.
---

# Tests

Write tests that follow `.claude/rules/tests.md`. Two modes:

- **TDD (default for new behaviour):** the code does not exist yet. Write the failing tests first, run them, and confirm they fail for the right reason (missing name or wrong result, not a typo in the test). Then stop and hand over to the implementation step, unless the user asked you to implement too.
- **Coverage (existing code):** the code exists but tests are missing or weak. Add tests for uncovered behaviour and run them; they should pass. If one fails, you found a bug: report it, do not change the test to match the bug.

## Steps
1. **Find the expected behaviour** in `docs/specs/01-bot-arena-design.md` and the current plan in `docs/plans/`. The spec decides what is correct, not the current code.
2. **List the behaviours** to test before writing code: the normal case, edge cases (map borders, walls, empty inputs, limits like 3 carried crystals or 3 active traps, turn 200/300), and error cases. Show this list in your reply.
3. **Write the unit tests** in `tests/test_<module>.py`:
   - `unittest` only; one behaviour per test method, named `test_<what_happens>`.
   - Arrange–act–assert, with small helper builders (e.g. a function that makes a tiny map from a few strings) instead of large fixtures.
   - `self.subTest` for the same behaviour over several inputs.
   - Fixed seeds for anything random; no real sleeps.
   - Annotate every test method `-> None`.
4. **Write doctests** in the docstrings of pure functions with simple inputs (one or two examples that also document usage). `tests/test_doctests.py` picks them up automatically; do not duplicate them as unit tests.
5. **Run** `../venv/Scripts/python -m unittest discover -s tests` and report which tests fail or pass and why.

## Report
List the tests added (file and method names), the result of the run, and any behaviour from the spec you could not test yet and why.

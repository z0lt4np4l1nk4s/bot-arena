---
paths:
  - "tests/**/*.py"
---

# Test rules

- Test-driven development: write the failing test first and run it to see it fail for the right reason, then write the code.
- Unit tests live in `tests/test_<module>.py` and use `unittest` only (no pytest).
- One behaviour per test method; the name says what it checks: `test_moving_into_wall_keeps_position`.
- Use `self.subTest(...)` when checking the same behaviour over several inputs.
- Tests are deterministic: random maps always come from a fixed seed; no real sleeps or wall-clock timing unless the test is about timing.
- No test depends on another test or on test order. Use `setUp` for shared fixtures.
- Test methods are fully annotated (`-> None`) like all other code; docstrings are optional in tests.
- Doctests stay in the source docstrings; `tests/test_doctests.py` collects them, so do not duplicate them as unit tests.

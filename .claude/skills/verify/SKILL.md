---
name: verify
description: Run every quality gate of Bot Arena (unit tests + doctests, ruff lint and format, pycodestyle, mypy strict, standard-library-only imports) and report pass/fail with the exact failures. Use before every commit, after finishing a task or plan step, and whenever asked to check, verify or validate the code.
---

# Verify

Run all quality gates from the project root (the folder containing `pyproject.toml`) and report the result. Do not fix anything unless the user asked for fixes; report first.

## Steps

Run each command and record its exit code and output. Run all of them even if an earlier one fails.

1. Tests (unittest + doctests):
   `../venv/Scripts/python -m unittest discover -s tests`
2. Lint: `../venv/Scripts/ruff check .`
3. Format: `../venv/Scripts/ruff format --check .`
4. PEP 8: `../venv/Scripts/pycodestyle src tests`
5. Types: `../venv/Scripts/mypy`
6. Standard library only:
   `../venv/Scripts/python .claude/skills/verify/check_imports.py src`
7. Smoke test, only once `src/main.py` exists: import every module under `src/arena`
   without starting the GUI:
   `../venv/Scripts/python -c "import importlib, pkgutil, arena; [importlib.import_module(m.name) for m in pkgutil.walk_packages(arena.__path__, 'arena.')]"`

## Report

Reply with a table, one row per gate: name, PASS/FAIL, and a one-line summary (e.g. "52 tests OK", "3 errors in src/arena/engine/turns.py").
For each failure, list the exact messages with `file:line`, grouped by file. Keep the full output short: show the failures, not the passing noise.

End with one line: **ALL GATES PASS** or **N GATES FAIL**.

Notes:
- VS Code Pylance (type checking `standard`) cannot be run from the command line here. If mypy strict passes, Pylance standard normally passes too; mention that it was not run.
- A gate that cannot run (missing tool, missing folder) counts as FAIL; say why.

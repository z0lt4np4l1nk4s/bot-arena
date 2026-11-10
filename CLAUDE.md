# Bot Arena

Desktop app (Python + tkinter) where users write Python bots that compete on a 20×20 grid.
Design spec (source of truth): `docs/specs/01-bot-arena-design.md`. Implementation plans: `docs/plans/`.

## Layout
- `src/arena/` – application package (`src/main.py` will be the entry point)
- `tests/` – unittest tests (`test_<module>.py`); `tests/test_doctests.py` collects all doctests
- `docs/specs/`, `docs/plans/` – numbered documents (`01-...md`), no dates in file names
- `.claude/rules/` – path-scoped coding rules (`python.md` for `src/`, `tests.md` for `tests/`)
- `.claude/skills/` – project skills (`verify`, `generate-tests`); `.claude/agents/reviewer.md` – independent review agent

## Ground rules
- Python **3.10** only; no 3.11+ features (`typing.Self`, `except*`, `tomllib`, ...).
- **Standard library only** at runtime. `requirements.txt` lists development tools only.
- **Everything in English**: code, comments, docstrings, GUI text, messages, docs, file names.
- **Test-driven development**: failing test first, then the minimum code, then refactor.
- Dependencies point one way: `gui → runtime/storage → engine → model`. The engine never imports the GUI.

## Quality gates
All must pass before a commit. Run from this folder with the virtualenv at `../venv`:

| Check | Command |
|---|---|
| Tests (unittest + doctest) | `../venv/Scripts/python -m unittest discover -s tests` |
| Lint | `../venv/Scripts/ruff check .` |
| Format | `../venv/Scripts/ruff format --check .` |
| PEP 8 | `../venv/Scripts/pycodestyle src tests` |
| Types | `../venv/Scripts/mypy` (strict) |
| Editor | VS Code Pylance, type checking `standard`, zero errors |

Settings live in `pyproject.toml` (ruff, mypy, Pylance) and `setup.cfg` (pycodestyle).
`src/` is on the import path through `../venv/Lib/site-packages/bot_arena_src.pth` (one line: the absolute path of `src/`), so tests can import `arena`. Nothing is installed and no build files are created.
Never silence a rule (`# noqa`, `# type: ignore`) without a comment explaining why.

## Git
- Every commit passes all quality gates.

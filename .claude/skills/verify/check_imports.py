"""Fail if any module under the given folder imports a non-stdlib package.

Usage: ``python check_imports.py <folder>``. Imports of the project package
``arena`` and relative imports are allowed.
"""

import ast
import sys
from pathlib import Path

ALLOWED_PROJECT_PACKAGES: frozenset[str] = frozenset({"arena"})


def imported_top_level_names(source: str) -> set[str]:
    r"""Return the top-level package names imported by a module.

    Args:
        source: Python source code.

    Returns:
        Names such as ``"os"`` for ``import os.path``; relative imports
        are skipped.

    >>> sorted(imported_top_level_names("import os.path\nfrom . import x"))
    ['os']
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add((node.module or "").split(".")[0])
    return names


def main(folder: Path) -> int:
    """Check every ``.py`` file under ``folder`` and print violations.

    Args:
        folder: The folder to scan recursively.

    Returns:
        The process exit code: 0 if all imports are allowed, 1 otherwise.
    """
    allowed = set(sys.stdlib_module_names) | ALLOWED_PROJECT_PACKAGES
    violations = 0
    for path in sorted(folder.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for name in sorted(imported_top_level_names(source) - allowed):
            print(f"{path}: imports non-stdlib package '{name}'")
            violations += 1
    print("OK: standard library only" if violations == 0 else "FAILED")
    return 0 if violations == 0 else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))

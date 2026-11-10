---
paths:
  - "src/**/*.py"
---

# Python code rules

## Formatting and naming (PEP 8)
- Maximum line length **79**. Formatting is done by `ruff format`.
- Imports at the top in two groups: standard library, then project modules. Absolute imports only (`from arena.model.geometry import Position`).
- `snake_case` for functions, methods, variables, modules; `PascalCase` for classes; `UPPER_CASE` for constants; leading `_` for private names.
- Names describe meaning, not type: `crystals_carried`, not `int_value` or `lst`. Full words, no abbreviations (`map_generator`, not `mapgen`).

## Type annotations (PEP 484, PEP 526)
- **Every** function and method has annotated parameters and a return type, including `-> None`.
- Module-level and class-level variables are annotated (`MAX_TURNS: Final = 200`).
- Modern 3.10 syntax: `list[int]`, `dict[str, int]`, `X | None`.
- Use the right `typing` tool: `Final` for constants, `ClassVar` for class attributes, `TypeAlias` for aliases, `Protocol` for structural interfaces, `TypeVar`/`ParamSpec` for generic functions and decorators, `Literal` for fixed string values.
- Avoid `Any`. When unavoidable (data from a user bot), keep it at the boundary and convert it to a typed value immediately.

## Docstrings and comments
- Every module, public class and public function has a Google-style docstring (`Args:`, `Returns:`, `Raises:`).
- Pure functions with simple inputs include **doctest** examples.
- Comments explain *why*, not *what*. No commented-out code.

## Design
- Value objects are immutable: `@dataclass(frozen=True)`.
- Small functions with one job. If a function needs comments to separate its sections, split it.
- No global mutable state; configuration is passed in.
- No `print` in library code. Log only through `arena.utilities.logger.get_logger("<component>")`; never import `logging` anywhere else (levels, format and file are configured in that one module).
- Catch specific exceptions only, never a bare `except:`. Project errors derive from `ArenaError`.
- Advanced techniques (decorators, closures, protocols/ABCs, concurrency, design patterns, metaprogramming) are used where the design spec places them, never forced in elsewhere.

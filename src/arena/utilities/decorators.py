"""Decorators used across the application.

``memoize`` keeps its cache in a closure, ``measure_time`` wraps a result
together with how long it took, and ``log_exceptions`` is a parameterized
decorator that logs any exception before letting it propagate.
"""

import functools
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Generic, ParamSpec, Protocol, TypeVar

from arena.utilities.logger import get_logger

P = ParamSpec("P")
R = TypeVar("R")
R_co = TypeVar("R_co", covariant=True)


class Memoized(Protocol[P, R_co]):
    """A memoized function: callable, with access to its cache."""

    __name__: str

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R_co:
        """Call the function, using the cache when possible."""
        ...

    def cache_size(self) -> int:
        """Return how many results are cached."""
        ...

    def cache_clear(self) -> None:
        """Forget every cached result."""
        ...


def memoize(function: Callable[P, R]) -> Memoized[P, R]:
    """Cache a function's results by its (hashable) arguments.

    The cache is a dictionary that lives in the enclosing scope of the
    wrapper, i.e. it is held by a closure.

    >>> @memoize
    ... def slow_square(number: int) -> int:
    ...     return number * number
    >>> slow_square(4), slow_square(4), slow_square.cache_size()
    (16, 16, 1)
    """
    cache: dict[Hashable, R] = {}

    @functools.wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        key = (args, frozenset(kwargs.items()))
        if key not in cache:
            cache[key] = function(*args, **kwargs)
        return cache[key]

    def cache_size() -> int:
        return len(cache)

    def cache_clear() -> None:
        cache.clear()

    # Functions accept new attributes; the Protocol describes the result.
    wrapper.cache_size = cache_size  # type: ignore[attr-defined]
    wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
    memoized: Memoized[P, R] = wrapper  # type: ignore[assignment]
    return memoized


@dataclass(frozen=True)
class Timed(Generic[R]):
    """A result together with the time it took, in milliseconds."""

    value: R
    elapsed_ms: float


def measure_time(function: Callable[P, R]) -> Callable[P, Timed[R]]:
    """Make a function also report how long each call took.

    >>> timed_sum = measure_time(sum)
    >>> timed_sum([1, 2, 3]).value
    6
    """

    @functools.wraps(function)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> Timed[R]:
        start = time.perf_counter()
        value = function(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return Timed(value, elapsed_ms)

    return wrapper


def log_exceptions(
    component: str,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Log any exception raised by the decorated function, then re-raise.

    Args:
        component: The part of the application, e.g. ``"runtime"``;
            the error goes to its logger (see :func:`get_logger`).

    Returns:
        The decorator.
    """
    logger = get_logger(component)

    def decorator(function: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(function)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return function(*args, **kwargs)
            except Exception:
                logger.exception(
                    "unexpected error in %s", function.__qualname__
                )
                raise

        return wrapper

    return decorator

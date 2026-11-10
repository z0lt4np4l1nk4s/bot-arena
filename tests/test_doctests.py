"""Run the doctests of every module in the ``arena`` package."""

import doctest
import importlib
import pkgutil
import unittest

import arena


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    """Add one doctest suite per ``arena`` module (unittest protocol).

    Args:
        loader: The loader running the discovery (unused).
        tests: The tests already collected from this module.
        pattern: The discovery pattern (unused).

    Returns:
        The collected tests extended with all doctests.
    """
    del loader, pattern
    for module_info in pkgutil.walk_packages(arena.__path__, prefix="arena."):
        module = importlib.import_module(module_info.name)
        tests.addTests(doctest.DocTestSuite(module))
    return tests

"""Tests for the decorators in arena.utilities."""

import time
import unittest

from arena.utilities.decorators import log_exceptions, measure_time, memoize


class MemoizeTest(unittest.TestCase):
    def test_memoize_calls_function_once_per_argument(self) -> None:
        calls: list[int] = []

        @memoize
        def square(number: int) -> int:
            calls.append(number)
            return number * number

        self.assertEqual(square(3), 9)
        self.assertEqual(square(3), 9)
        self.assertEqual(len(calls), 1)
        square(4)
        self.assertEqual(len(calls), 2)

    def test_memoize_keyword_arguments_are_part_of_key(self) -> None:
        @memoize
        def power(base: int, exponent: int = 2) -> int:
            return int(base**exponent)

        self.assertEqual(power(2), 4)
        self.assertEqual(power(2, exponent=3), 8)
        self.assertEqual(power.cache_size(), 2)

    def test_memoize_cache_clear(self) -> None:
        @memoize
        def identity(value: int) -> int:
            return value

        identity(1)
        identity.cache_clear()
        self.assertEqual(identity.cache_size(), 0)

    def test_memoize_keeps_name_and_docstring(self) -> None:
        @memoize
        def documented(value: int) -> int:
            """Return the value."""
            return value

        self.assertEqual(documented.__name__, "documented")
        self.assertEqual(documented.__doc__, "Return the value.")


class MeasureTimeTest(unittest.TestCase):
    def test_measure_time_returns_value_and_elapsed(self) -> None:
        @measure_time
        def slow(value: int) -> int:
            time.sleep(0.02)
            return value

        timed = slow(5)
        self.assertEqual(timed.value, 5)
        self.assertGreaterEqual(timed.elapsed_ms, 15)


class LogExceptionsTest(unittest.TestCase):
    def test_log_exceptions_logs_traceback_and_reraises(self) -> None:
        @log_exceptions("test")
        def divide(number: int) -> float:
            return 1 / number

        with (
            self.assertLogs("arena.test", "ERROR") as logs,
            self.assertRaises(ZeroDivisionError),
        ):
            divide(0)
        output = "\n".join(logs.output)
        self.assertIn("divide", output)
        self.assertIn("ZeroDivisionError", output)

    def test_log_exceptions_passes_results_through(self) -> None:
        @log_exceptions("test")
        def double(number: int) -> int:
            return number * 2

        self.assertEqual(double(4), 8)


if __name__ == "__main__":
    unittest.main()

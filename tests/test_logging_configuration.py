"""Tests for the configurable logging levels."""

import logging
import tempfile
import unittest
from pathlib import Path

from arena.utilities.logging_configuration import (
    LogLevel,
    LogSettings,
    configure_logging,
)


class ConfigureLoggingTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.log_file = Path(directory.name) / "test.log"
        self.logger = logging.getLogger("arena.example")

    def tearDown(self) -> None:
        arena_logger = logging.getLogger("arena")
        for handler in list(arena_logger.handlers):
            handler.close()
            arena_logger.removeHandler(handler)
        arena_logger.setLevel(logging.NOTSET)

    def written(self) -> str:
        """Return what the log file contains after flushing."""
        for handler in logging.getLogger("arena").handlers:
            handler.flush()
        return self.log_file.read_text(encoding="utf-8")

    def configure(self, level: LogLevel) -> None:
        """Configure logging to the temporary file at ``level``."""
        configure_logging(LogSettings(level, self.log_file))

    def test_warning_level_skips_info(self) -> None:
        self.configure(LogLevel.WARNING)
        self.logger.info("quiet info")
        self.logger.warning("loud warning")
        text = self.written()
        self.assertIn("loud warning", text)
        self.assertNotIn("quiet info", text)

    def test_debug_level_writes_everything(self) -> None:
        self.configure(LogLevel.DEBUG)
        self.logger.debug("tiny detail")
        self.assertIn("tiny detail", self.written())

    def test_error_level_writes_only_errors(self) -> None:
        self.configure(LogLevel.ERROR)
        self.logger.warning("not this")
        self.logger.error("only this")
        text = self.written()
        self.assertIn("only this", text)
        self.assertNotIn("not this", text)

    def test_reconfiguring_replaces_the_file_handler(self) -> None:
        self.configure(LogLevel.WARNING)
        self.configure(LogLevel.INFO)
        file_handlers = [
            handler
            for handler in logging.getLogger("arena").handlers
            if isinstance(handler, logging.FileHandler)
        ]
        self.assertEqual(len(file_handlers), 1)

    def test_default_settings(self) -> None:
        settings = LogSettings()
        self.assertIs(settings.level, LogLevel.WARNING)
        self.assertEqual(settings.log_file, Path("arena.log"))


class LogLevelTest(unittest.TestCase):
    def test_level_from_name_is_case_insensitive(self) -> None:
        self.assertIs(LogLevel.from_name("info"), LogLevel.INFO)
        self.assertIs(LogLevel.from_name("Debug"), LogLevel.DEBUG)

    def test_unknown_level_name_lists_valid_names(self) -> None:
        with self.assertRaises(ValueError) as context:
            LogLevel.from_name("loud")
        self.assertIn("ERROR, WARNING, INFO, DEBUG", str(context.exception))


if __name__ == "__main__":
    unittest.main()

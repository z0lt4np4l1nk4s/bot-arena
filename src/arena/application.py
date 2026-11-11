"""The composition root: the one place that puts the application together.

Everything else depends on abstractions (``GameMode``, ``BotClient``,
``MatchObserver``, ``MatchRepository``) and receives them from outside.
Only this module chooses the concrete classes: SQLite for storage, a
separate process for every bot, and the observer that saves matches.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from arena.bots.registry import builtin_bots
from arena.bots.source import BotSource
from arena.engine.modes import GameMode
from arena.model.side import Side
from arena.model.state import ModeKind
from arena.rules import DEFAULT_RULES, Rules
from arena.runtime.bot_process import BotProcess
from arena.runtime.clients import BotClient
from arena.runtime.match_runner import MatchRunner
from arena.runtime.observers import MatchObserver
from arena.storage.repository import MatchRepository
from arena.storage.sqlite_repository import SqliteMatchRepository
from arena.storage.storage_observer import StorageObserver
from arena.utilities.logger import (
    LogSettings,
    configure_logging,
    shutdown_logging,
)


@dataclass(frozen=True)
class ApplicationSettings:
    """Everything that can be configured when the application starts."""

    database: Path = Path("arena.db")
    rules: Rules = DEFAULT_RULES
    log_settings: LogSettings = field(default_factory=LogSettings)
    user_bots_folder: Path = Path("user_bots")


class Application:
    """Builds matches from settings; owns the match history."""

    def __init__(
        self,
        settings: ApplicationSettings,
        repository: MatchRepository | None = None,
    ) -> None:
        """Create the application.

        Args:
            settings: The configuration.
            repository: Storage to use instead of the SQLite database;
                tests pass an in-memory one.
        """
        self.settings = settings
        self.repository: MatchRepository = (
            repository
            if repository is not None
            else SqliteMatchRepository(settings.database)
        )
        self._logging_configured = False

    def configure(self) -> None:
        """Set up logging for this process."""
        configure_logging(self.settings.log_settings)
        self._logging_configured = True

    def bot_sources(self) -> list[BotSource]:
        """The built-in bots, then every user bot file, by name."""
        builtins = [BotSource.builtin(name) for name in sorted(builtin_bots())]
        folder = self.settings.user_bots_folder
        files = sorted(folder.glob("*.py")) if folder.is_dir() else []
        return [*builtins, *(BotSource.from_file(path) for path in files)]

    def create_match(
        self,
        mode: ModeKind,
        blue: BotSource,
        red: BotSource | None = None,
        observers: Sequence[MatchObserver] = (),
    ) -> MatchRunner:
        """Put together a match with real bot processes that is saved.

        Args:
            mode: Duel or solo.
            blue: The Blue bot.
            red: The Red bot (duel only).
            observers: Extra listeners, e.g. the GUI's queue observer.

        Returns:
            A runner ready to :meth:`~MatchRunner.run` the match.

        Raises:
            ValueError: If a duel has no Red bot.
        """
        game_mode = GameMode.create(mode, self.settings.rules)
        sources = {Side.BLUE: blue}
        if mode is ModeKind.DUEL:
            if red is None:
                message = "a duel needs a Red bot"
                raise ValueError(message)
            sources[Side.RED] = red
        clients: dict[Side, BotClient] = {
            side: BotProcess(
                source, self.settings.rules, self.settings.log_settings
            )
            for side, source in sources.items()
        }
        # The match is saved before anyone else hears that it ended, so a
        # listener can already find it in the history.
        return MatchRunner(
            game_mode,
            clients,
            [StorageObserver(self.repository), *observers],
        )

    def close(self) -> None:
        """Close the match history and the log file this object opened."""
        self.repository.close()
        if self._logging_configured:
            shutdown_logging()
            self._logging_configured = False

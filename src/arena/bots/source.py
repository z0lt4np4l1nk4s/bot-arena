"""Where a bot comes from: a built-in name or a user's file (a Factory).

A :class:`BotSource` is small and picklable, so it can be sent to another
process, which then creates the bot itself.
"""

from dataclasses import dataclass
from pathlib import Path

from arena.bots.loader import load_bot_class
from arena.bots.protocol import Bot
from arena.bots.registry import builtin_bots
from arena.errors import BotLoadError


@dataclass(frozen=True)
class BotSource:
    """A recipe for creating a bot; ``path`` is ``None`` for built-ins."""

    name: str
    path: Path | None = None

    @classmethod
    def builtin(cls, name: str) -> "BotSource":
        """The source of a built-in bot such as ``"Hard"``."""
        return cls(name)

    @classmethod
    def from_file(cls, path: Path) -> "BotSource":
        """The source of a user bot; its name is the file name."""
        return cls(path.stem, path)

    @property
    def is_builtin(self) -> bool:
        """Whether this is one of the built-in bots."""
        return self.path is None

    def create(self) -> Bot:
        """Create a new bot instance.

        Raises:
            BotLoadError: If the built-in name is unknown or the file
                cannot be loaded.
        """
        if self.path is not None:
            return load_bot_class(self.path)()
        bots = builtin_bots()
        if self.name not in bots:
            message = f"unknown built-in bot {self.name!r}"
            raise BotLoadError(message)
        return bots[self.name]()

"""Bot Arena entry point.

Without a command the window opens; ``play`` plays one match in the
terminal::

    python src/main.py
    python src/main.py gui --log-level info
    python src/main.py play Hard Medium --seed 3
    python src/main.py play user_bots/my_bot.py Hard
    python src/main.py play Medium --solo --log-level info

A bot is a built-in name (Easy, Medium, Hard) or a path to a ``.py`` file.
"""

import argparse
import contextlib
import ctypes
import random
import sys
import tkinter as tk
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from arena.application import Application, ApplicationSettings
from arena.bots.source import BotSource
from arena.errors import ArenaError
from arena.gui.main_window import MainWindow
from arena.gui.sounds import SoundEffects, choose_player
from arena.model.side import Side
from arena.model.state import ModeKind
from arena.storage.records import RecordedMatch
from arena.utilities.logger import LogLevel, LogSettings

# The project folder: history, log and user bots live here, wherever the
# program is started from.
PROJECT_FOLDER: Final = Path(__file__).resolve().parent.parent
HELP: Final = ("-h", "--help")


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the command line.

    Args:
        arguments: The command-line arguments; ``None`` uses ``sys.argv``.

    Returns:
        The exit code: 0 on success, 2 if a bot could not be used.
    """
    options = parse_arguments(arguments)
    settings = ApplicationSettings(
        database=Path(options.database),
        log_settings=LogSettings(
            LogLevel.from_name(options.log_level), Path(options.log_file)
        ),
        user_bots_folder=PROJECT_FOLDER / "user_bots",
    )
    application = Application(settings)
    application.configure()
    try:
        if options.command == "play":
            return _play(application, options)
        return run_window(application)
    finally:
        application.close()


def run_window(application: Application) -> int:
    """Open the main window and wait until it is closed.

    Args:
        application: The configured application.

    Returns:
        The exit code, 0.
    """
    _use_sharp_text_on_windows()
    root = tk.Tk()
    MainWindow(root, application, SoundEffects(choose_player()))
    root.mainloop()
    return 0


def _use_sharp_text_on_windows() -> None:
    """Ask Windows not to blur the window when the display is scaled."""
    if sys.platform == "win32":
        # Older Windows versions lack this call; they keep the default.
        with contextlib.suppress(AttributeError, OSError):
            ctypes.windll.shcore.SetProcessDpiAwareness(1)


def _play(application: Application, options: argparse.Namespace) -> int:
    """Play one match and print its result."""
    mode = ModeKind.SOLO if options.solo else ModeKind.DUEL
    seed = (
        options.seed if options.seed is not None else random.randrange(10**6)
    )
    red = None if options.solo else _source(options.red or "Medium")
    try:
        runner = application.create_match(mode, _source(options.blue), red)
        match = runner.run(seed)
    except ArenaError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"seed {seed}: {describe_result(match)}")
    return 0


def describe_result(match: RecordedMatch) -> str:
    """One line describing how a match ended.

    Returns:
        For example ``"Blue (Hard) wins 9:7 in 170 turns"``.
    """
    summary = match.summary
    if summary.mode is ModeKind.SOLO:
        bot = summary.bots[Side.BLUE]
        if summary.solo_turns_used is not None:
            return f"Solo ({bot}): finished in {summary.solo_turns_used} turns"
        total = match.initial_state.crystals_left
        delivered = summary.delivered[Side.BLUE]
        return f"Solo ({bot}): did not finish ({delivered} of {total})"
    blue, red = summary.delivered[Side.BLUE], summary.delivered[Side.RED]
    if summary.winner is None:
        return f"Draw {blue}:{red} in {summary.turns} turns"
    name = summary.winner.name.capitalize()
    bot = summary.bots[summary.winner]
    return f"{name} ({bot}) wins {blue}:{red} in {summary.turns} turns"


def _source(text: str) -> BotSource:
    """A built-in bot name or the path of a bot file."""
    path = Path(text)
    if path.suffix == ".py":
        return BotSource.from_file(path)
    return BotSource.builtin(text)


def parse_arguments(arguments: Sequence[str] | None) -> argparse.Namespace:
    """Read the command-line options; invalid ones exit with code 2.

    Without a command (or with only options) the window is opened.

    Args:
        arguments: The command-line arguments; ``None`` uses ``sys.argv``.

    Returns:
        The parsed options.
    """
    given = list(sys.argv[1:] if arguments is None else arguments)
    if not given or (given[0].startswith("-") and given[0] not in HELP):
        given.insert(0, "gui")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--log-level",
        default="warning",
        choices=[level.name.lower() for level in LogLevel],
        help="how much to write to the log (default: warning)",
    )
    common.add_argument(
        "--log-file", default=str(PROJECT_FOLDER / "arena.log")
    )
    common.add_argument("--database", default=str(PROJECT_FOLDER / "arena.db"))
    parser = argparse.ArgumentParser(
        prog="bot-arena",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "gui", parents=[common], help="open the window (the default)"
    )
    play = commands.add_parser(
        "play", parents=[common], help="play one match in the terminal"
    )
    play.add_argument("blue", help="Blue bot: a built-in name or a .py file")
    play.add_argument("red", nargs="?", help="Red bot (default: Medium)")
    play.add_argument("--seed", type=int, help="map seed (default: random)")
    play.add_argument("--solo", action="store_true", help="play solo")
    options = parser.parse_args(given)
    if options.command == "play" and options.solo and options.red:
        play.error("a solo match has no Red bot")
    return options


if __name__ == "__main__":
    raise SystemExit(main())

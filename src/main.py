"""Bot Arena entry point.

Until the window is ready, matches are played from the command line::

    python src/main.py play Hard Medium --seed 3
    python src/main.py play user_bots/my_bot.py Hard
    python src/main.py play Medium --solo --log-level info

A bot is a built-in name (Easy, Medium, Hard) or a path to a ``.py`` file.
"""

import argparse
import random
import sys
from collections.abc import Sequence
from pathlib import Path

from arena.application import Application, ApplicationSettings
from arena.bots.source import BotSource
from arena.errors import ArenaError
from arena.model.side import Side
from arena.model.state import ModeKind
from arena.storage.records import RecordedMatch
from arena.utilities.logger import LogLevel, LogSettings


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the command line.

    Args:
        arguments: The command-line arguments; ``None`` uses ``sys.argv``.

    Returns:
        The exit code: 0 on success, 2 if a bot could not be used.
    """
    options = _parser().parse_args(arguments)
    settings = ApplicationSettings(
        database=Path(options.database),
        log_settings=LogSettings(
            LogLevel.from_name(options.log_level), Path(options.log_file)
        ),
    )
    application = Application(settings)
    application.configure()
    try:
        return _play(application, options)
    finally:
        application.close()


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


def _parser() -> argparse.ArgumentParser:
    """The command-line options."""
    parser = argparse.ArgumentParser(prog="bot-arena", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    play = commands.add_parser("play", help="play one match")
    play.add_argument("blue", help="Blue bot: a built-in name or a .py file")
    play.add_argument("red", nargs="?", help="Red bot (default: Medium)")
    play.add_argument("--seed", type=int, help="map seed (default: random)")
    play.add_argument("--solo", action="store_true", help="play solo")
    play.add_argument(
        "--log-level",
        default="warning",
        help="error, warning, info or debug (default: warning)",
    )
    play.add_argument("--log-file", default="arena.log")
    play.add_argument("--database", default="arena.db")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())

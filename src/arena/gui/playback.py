"""Which turn the match viewer shows, and whether it is playing.

:class:`Playback` is a small state machine without any widgets: the
viewer's buttons, sliders and timer only call its methods and then draw
the turn it points at. Turn 0 is the start of the match.
"""

from collections.abc import Callable
from typing import Final

SPEED_RANGE: Final = (1, 20)
DEFAULT_SPEED: Final = 5


class Playback:
    """The viewer's position in a match that may still be running.

    >>> playback = Playback(max_turns=200, available=3, finished=True)
    >>> playback.next()
    >>> playback.label
    'Turn 1 / 3'
    """

    def __init__(
        self,
        max_turns: int,
        available: int = 0,
        finished: bool = False,
        playing: bool = False,
    ) -> None:
        """Start at turn 0.

        Args:
            max_turns: The turn limit of the match.
            available: How many turns have been played so far.
            finished: Whether no more turns will come.
            playing: Whether to move forward on every tick.
        """
        self.max_turns = max_turns
        self.available = available
        self.finished = finished
        self.playing = playing
        self.current = 0

    @property
    def label(self) -> str:
        """The turn counter, for example ``"Turn 47 / 200"``.

        While the match runs the total is the turn limit; afterwards it is
        the number of turns actually played.
        """
        total = self.available if self.finished else self.max_turns
        return f"Turn {self.current} / {total}"

    def first(self) -> None:
        """Go to the start and pause."""
        self.jump(0)

    def previous(self) -> None:
        """Go one turn back and pause."""
        self.jump(self.current - 1)

    def next(self) -> None:
        """Go one turn forward and pause."""
        self.jump(self.current + 1)

    def jump(self, turn: int) -> None:
        """Go to ``turn`` (kept within the played turns) and pause."""
        self.current = max(0, min(turn, self.available))
        self.playing = False

    def last(self) -> None:
        """Go to the newest turn; keep following it while the match runs."""
        self.current = self.available
        self.playing = not self.finished

    def toggle(self) -> None:
        """Play or pause; playing at the end of a match starts it again."""
        if self.playing:
            self.playing = False
            return
        if self.finished and self.current >= self.available:
            self.current = 0
        self.playing = True

    def add_turn(self) -> None:
        """A new turn was played; while playing, a later tick shows it.

        Live turns are shown at the playback speed like a replay, because
        bots often play much faster than anyone can watch.
        """
        self.available += 1

    def finish(self) -> None:
        """No more turns will come."""
        self.finished = True

    def tick(self) -> bool:
        """Move one turn forward if playing and there is a turn to show.

        Returns:
            Whether the current turn changed.
        """
        if self.playing and self.current < self.available:
            self.current += 1
            return True
        if self.finished:
            self.playing = False
        return False


def make_jump_to(playback: Playback, turn: int) -> Callable[[], None]:
    """A callback that shows ``turn``, e.g. for a row of the turn log.

    The returned function is a closure over ``playback`` and ``turn``.

    >>> playback = Playback(max_turns=200, available=9, finished=True)
    >>> show_turn_four = make_jump_to(playback, 4)
    >>> show_turn_four()
    >>> playback.current
    4
    """

    def jump_to() -> None:
        playback.jump(turn)

    return jump_to


def tick_delay_ms(speed: int) -> int:
    """Milliseconds between two turns at ``speed`` turns per second.

    The speed is kept within :data:`SPEED_RANGE`.

    >>> tick_delay_ms(5)
    200
    >>> tick_delay_ms(0), tick_delay_ms(100)
    (1000, 50)
    """
    lowest, highest = SPEED_RANGE
    return 1000 // max(lowest, min(speed, highest))

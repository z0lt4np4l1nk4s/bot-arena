"""Helpers that build small game states for tests from text pictures."""

from collections.abc import Sequence
from dataclasses import replace

from arena.model.geometry import Position
from arena.model.side import Side
from arena.model.state import GameMap, GameState, ModeKind, PlayerState
from arena.rules import DEFAULT_RULES, Rules

_BOT_LETTERS = {"B": Side.BLUE, "R": Side.RED}


def make_state(
    rows: Sequence[str],
    *,
    max_turns: int = 200,
    rules: Rules = DEFAULT_RULES,
) -> GameState:
    """Build a game state from a square text picture.

    ``#`` is a wall, ``B``/``R`` the Blue/Red bot, ``*`` one crystal,
    ``2``-``9`` that many crystals and ``.`` an empty cell. Bases are always
    in the top-left and bottom-right corners. Without ``R`` the mode is solo.

    Args:
        rows: One string per grid row, all of the same length.
        max_turns: The turn limit of the state.
        rules: Used for the number of free traps each bot starts with.

    Returns:
        A state at turn 0.
    """
    size = len(rows)
    walls: set[Position] = set()
    crystals: dict[Position, int] = {}
    players: dict[Side, PlayerState] = {}
    for y, row in enumerate(rows):
        for x, char in enumerate(row):
            cell = Position(x, y)
            if char == "#":
                walls.add(cell)
            elif char == "*":
                crystals[cell] = 1
            elif char.isdigit():
                crystals[cell] = int(char)
            elif char in _BOT_LETTERS:
                side = _BOT_LETTERS[char]
                players[side] = PlayerState(
                    side, cell, free_traps=rules.traps_per_bot
                )
    bases = {
        Side.BLUE: Position(0, 0),
        Side.RED: Position(size - 1, size - 1),
    }
    return GameState(
        mode=ModeKind.DUEL if Side.RED in players else ModeKind.SOLO,
        turn=0,
        max_turns=max_turns,
        map=GameMap(size, frozenset(walls), bases),
        crystals=crystals,
        players=players,
    )


def with_player(  # noqa: PLR0913 - one keyword per field is clearest
    state: GameState,
    side: Side,
    *,
    position: Position | None = None,
    carrying: int | None = None,
    delivered: int | None = None,
    shoot_cooldown: int | None = None,
    stunned_turns: int | None = None,
    trapped_turns: int | None = None,
    free_traps: int | None = None,
    trap_cooldown: int | None = None,
    last_delivery_turn: int | None = None,
) -> GameState:
    """Return ``state`` with some fields of one player changed."""
    old = state.players[side]
    new = PlayerState(
        side=side,
        position=old.position if position is None else position,
        carrying=old.carrying if carrying is None else carrying,
        delivered=old.delivered if delivered is None else delivered,
        shoot_cooldown=(
            old.shoot_cooldown if shoot_cooldown is None else shoot_cooldown
        ),
        stunned_turns=(
            old.stunned_turns if stunned_turns is None else stunned_turns
        ),
        trapped_turns=(
            old.trapped_turns if trapped_turns is None else trapped_turns
        ),
        free_traps=old.free_traps if free_traps is None else free_traps,
        trap_cooldown=(
            old.trap_cooldown if trap_cooldown is None else trap_cooldown
        ),
        last_delivery_turn=(
            old.last_delivery_turn
            if last_delivery_turn is None
            else last_delivery_turn
        ),
    )
    return replace(state, players={**state.players, side: new})


def with_crystals(
    state: GameState, crystals: dict[Position, int]
) -> GameState:
    """Return ``state`` with a different set of crystals on the ground."""
    return replace(state, crystals=crystals)

"""Play whole matches in one process, for testing bot behaviour."""

from arena.bots.protocol import Bot
from arena.engine.modes import Duel
from arena.model.side import Side
from arena.model.state import GameState
from arena.rules import DEFAULT_RULES, Rules


def play_duel(
    blue: Bot, red: Bot, seed: int, rules: Rules = DEFAULT_RULES
) -> GameState:
    """Play a full duel without processes or time limits.

    Args:
        blue: The bot playing Blue.
        red: The bot playing Red.
        seed: The map seed.
        rules: The rules of the match.

    Returns:
        The final state.
    """
    duel = Duel(rules)
    state = duel.setup_map(seed)
    bots = {Side.BLUE: blue, Side.RED: red}
    while not duel.is_over(state):
        actions = {
            side: bot.decide(duel.state_for_bot(state, side))
            for side, bot in bots.items()
        }
        state = duel.step(state, actions)
    return state


def wins(first: type[Bot], second: type[Bot], seeds: range) -> tuple[int, int]:
    """Count wins of ``first`` and ``second`` over seeds and both sides.

    Returns:
        ``(wins of first, wins of second)``; draws count for neither.
    """
    duel = Duel()
    first_wins = second_wins = 0
    for seed in seeds:
        for first_side in Side:
            bots = {first_side: first(), first_side.opponent: second()}
            final = play_duel(bots[Side.BLUE], bots[Side.RED], seed)
            winner = duel.winner(final)
            if winner is first_side:
                first_wins += 1
            elif winner is first_side.opponent:
                second_wins += 1
    return first_wins, second_wins

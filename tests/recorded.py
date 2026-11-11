"""A real recorded match for storage tests, played in one process."""

from datetime import datetime

from arena.bots.builtin.hard import HardBot
from arena.engine.modes import Duel
from arena.model.actions import Action
from arena.model.side import Side
from arena.rules import Rules
from arena.runtime.bot_process import BotReply
from arena.storage.records import MatchSummary, RecordedMatch, TurnRecord

# Seed 7 with two Hard bots has traps, a hit with dropped crystals, a
# refused action and deliveries within the first 180 turns.
SEED = 7
TURNS = 180


def record_match(seed: int = SEED, turns: int = TURNS) -> RecordedMatch:
    """Play a Hard vs Hard duel and record it turn by turn.

    Turn 2 gets an error reply for Red and turn 3 a timed-out reply for
    Blue, so stored data covers every kind of reply.
    """
    duel = Duel(Rules(duel_max_turns=turns))
    initial = duel.setup_map(seed)
    bots = {Side.BLUE: HardBot(), Side.RED: HardBot()}
    state = initial
    records: list[TurnRecord] = []
    while not duel.is_over(state):
        number = state.turn + 1
        replies = {
            side: _reply(
                number, side, bot.decide(duel.state_for_bot(state, side))
            )
            for side, bot in bots.items()
        }
        state = duel.step(
            state, {side: reply.action for side, reply in replies.items()}
        )
        records.append(TurnRecord(number, state, replies))
    summary = MatchSummary(
        match_id=None,
        played_at=datetime(2026, 11, 11, 12, 0, 0),
        mode=initial.mode,
        seed=seed,
        bots={Side.BLUE: "Hard", Side.RED: "Hard"},
        winner=duel.winner(state),
        delivered={side: state.player(side).delivered for side in Side},
        turns=state.turn,
        solo_turns_used=None,
    )
    return RecordedMatch(summary, initial, tuple(records))


def _reply(turn: int, side: Side, action: Action) -> BotReply:
    """Wrap an action, injecting one error and one timeout."""
    if turn == 2 and side is Side.RED:
        return BotReply(
            turn,
            Action.wait(),
            0.0,
            error="ZeroDivisionError: division by zero (line 9)",
        )
    if turn == 3 and side is Side.BLUE:
        return BotReply(turn, Action.wait(), 100.0, timed_out=True)
    return BotReply(turn, action, 1.25 + turn / 100)

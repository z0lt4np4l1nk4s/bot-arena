"""The Match Viewer tab: watch a match live or step through a replay.

The map is on the left with the playback controls below it, the turn log
is on the right and the score and both bots' state are on top. Which
turn is shown is decided by a :class:`~arena.gui.playback.Playback`;
this widget only draws it.
"""

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import Final

from arena.gui.formatting import log_rows, player_status, score_text
from arena.gui.icons import IconButton, IconName
from arena.gui.map_canvas import SIDE_COLOURS, MapCanvas
from arena.gui.playback import (
    DEFAULT_SPEED,
    SPEED_RANGE,
    Playback,
    make_jump_to,
    tick_delay_ms,
)
from arena.model.side import Side
from arena.model.state import GameState
from arena.rules import Rules
from arena.storage.records import MatchSummary, RecordedMatch, TurnRecord

LOG_COLUMNS: Final = (
    ("turn", "Turn", 50),
    ("bot", "Bot", 50),
    ("action", "Action", 110),
    ("message", "Message", 150),
    ("thinking", "Thinking (ms)", 105),
    ("problem", "Problem", 150),
)
PROBLEM_BACKGROUND: Final = "#fbe3e3"
CURRENT_BACKGROUND: Final = "#fff4c2"


class MatchViewer(ttk.Frame):
    """Shows one match at a time, live or recorded."""

    def __init__(self, master: tk.Misc, rules: Rules) -> None:
        """Create an empty viewer.

        Args:
            master: The parent widget.
            rules: The rules of the matches that will be shown.
        """
        super().__init__(master, padding=8)
        self.rules = rules
        self.is_live = False
        self.match_id: int | None = None
        self.playback: Playback | None = None
        self._initial: GameState | None = None
        self._records: list[TurnRecord] = []
        self._jumps: dict[str, Callable[[], None]] = {}
        self._rows_of_turn: dict[int, list[str]] = {}
        self._speed = DEFAULT_SPEED
        self._moving_slider = False
        self._timer: str | None = None
        self._build_header()
        self._build_map_and_controls()
        self._build_log()
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self.clear()
        self._schedule_tick()

    def start_live(
        self, summary: MatchSummary, initial_state: GameState
    ) -> None:
        """Begin showing a match that is being played right now."""
        self._reset(summary, initial_state)
        self.is_live = True
        self.playback = Playback(initial_state.max_turns, playing=True)
        self._refresh()

    def add_turn(self, record: TurnRecord) -> None:
        """Add a turn of the live match."""
        if self.playback is None:
            return
        self._append(record)
        self.playback.add_turn()
        self._refresh()

    def finish_live(
        self, match: RecordedMatch, match_id: int | None = None
    ) -> None:
        """The live match ended; ``match_id`` is its id in the history."""
        if self.playback is None:
            return
        missing = len(self._records)
        for record in match.turns[missing:]:
            self._append(record)
            self.playback.add_turn()
        self.playback.finish()
        self.is_live = False
        self.match_id = match_id
        self._refresh()

    def show_recorded(self, match: RecordedMatch) -> None:
        """Show a finished match from the start, paused."""
        self._reset(match.summary, match.initial_state)
        for record in match.turns:
            self._append(record)
        self.playback = Playback(
            match.initial_state.max_turns,
            available=len(match.turns),
            finished=True,
        )
        self.match_id = match.summary.match_id
        self._refresh()

    def clear(self) -> None:
        """Show no match at all."""
        self._reset(None, None)
        self.playback = None
        self.map_canvas.draw(None)
        self.title_label.configure(text="No match selected")
        self.score_label.configure(text="")
        for label in self.status_labels.values():
            label.configure(text="")
        self.turn_label.configure(text="Turn 0 / 0")
        self._set_controls_enabled(False)

    def destroy(self) -> None:
        """Stop the playback timer before the widget goes away."""
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None
        super().destroy()

    def current_state(self) -> GameState | None:
        """The state of the turn being shown."""
        if self.playback is None or self._initial is None:
            return None
        turn = self.playback.current
        return self._initial if turn == 0 else self._records[turn - 1].state

    def _build_header(self) -> None:
        """The match title, the score and one status line per bot."""
        header = ttk.Frame(self)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.title_label = ttk.Label(header, font=("TkDefaultFont", 11))
        self.title_label.pack(side="left")
        self.score_label = ttk.Label(
            header, font=("TkDefaultFont", 16, "bold")
        )
        self.score_label.pack(side="left", padx=24)
        self.status_labels: dict[Side, ttk.Label] = {}
        for side in Side:
            label = ttk.Label(header, foreground=SIDE_COLOURS[side])
            label.pack(side="left", padx=8)
            self.status_labels[side] = label

    def _build_map_and_controls(self) -> None:
        """The map with the playback buttons and sliders under it."""
        left = ttk.Frame(self)
        left.grid(row=1, column=0, sticky="nsew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.map_canvas = MapCanvas(left, self.rules)
        self.map_canvas.grid(row=0, column=0, sticky="nsew")
        controls = ttk.Frame(left, padding=(0, 6))
        controls.grid(row=1, column=0, sticky="ew")
        self.buttons: list[IconButton] = []
        self.first_button = self._button(
            controls, IconName.FIRST, "First turn", self._on_first
        )
        self.previous_button = self._button(
            controls, IconName.PREVIOUS, "Previous turn", self._on_previous
        )
        self.play_button = self._button(
            controls, IconName.PLAY, "Play or pause", self._on_toggle
        )
        self.next_button = self._button(
            controls, IconName.NEXT, "Next turn", self._on_next
        )
        self.last_button = self._button(
            controls, IconName.LAST, "Newest turn", self._on_last
        )
        self.turn_label = ttk.Label(controls, width=16, anchor="center")
        self.turn_label.pack(side="left", padx=8)
        self.turn_slider = ttk.Scale(
            controls, from_=0, to=1, command=self._on_turn_slider
        )
        self.turn_slider.pack(side="left", fill="x", expand=True)
        ttk.Label(controls, text="Speed").pack(side="left", padx=(12, 4))
        lowest, highest = SPEED_RANGE
        self.speed_slider = ttk.Scale(
            controls,
            from_=lowest,
            to=highest,
            length=110,
            command=self._on_speed_slider,
        )
        self.speed_slider.set(DEFAULT_SPEED)
        self.speed_slider.pack(side="left")
        self.hint_label = ttk.Label(left, foreground="#666666")
        self.hint_label.grid(row=2, column=0, sticky="w")

    def _button(
        self,
        parent: tk.Misc,
        icon: IconName,
        tooltip: str,
        command: Callable[[], None],
    ) -> IconButton:
        """An icon button whose description appears under the map."""
        button = IconButton(parent, icon, command, tooltip)
        button.pack(side="left", padx=2)
        button.bind(
            "<Enter>",
            lambda _event: self.hint_label.configure(text=tooltip),
            add="+",
        )
        button.bind(
            "<Leave>",
            lambda _event: self.hint_label.configure(text=""),
            add="+",
        )
        self.buttons.append(button)
        return button

    def _build_log(self) -> None:
        """The turn log: one row per bot and turn."""
        frame = ttk.Frame(self, padding=(8, 0, 0, 0))
        frame.grid(row=1, column=1, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.log = ttk.Treeview(
            frame,
            columns=[name for name, _, _ in LOG_COLUMNS],
            show="headings",
            selectmode="browse",
        )
        for name, heading, width in LOG_COLUMNS:
            self.log.heading(name, text=heading)
            self.log.column(name, width=width, stretch=name == "message")
        for side in Side:
            self.log.tag_configure(side.value, foreground=SIDE_COLOURS[side])
        self.log.tag_configure("problem", background=PROBLEM_BACKGROUND)
        self.log.tag_configure("current", background=CURRENT_BACKGROUND)
        scrollbar = ttk.Scrollbar(
            frame, orient="vertical", command=self.log.yview
        )
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.bind("<<TreeviewSelect>>", self._on_log_select)

    def _reset(
        self, summary: MatchSummary | None, initial: GameState | None
    ) -> None:
        """Forget the shown match and empty the log."""
        self.is_live = False
        self.match_id = None
        self._initial = initial
        self._records = []
        self._jumps = {}
        self._rows_of_turn = {}
        self.log.delete(*self.log.get_children())
        if summary is not None:
            bots = " vs ".join(summary.bots[side] for side in summary.bots)
            mode = summary.mode.value.capitalize()
            self.title_label.configure(
                text=f"{mode}: {bots} · seed {summary.seed}"
            )

    def _append(self, record: TurnRecord) -> None:
        """Remember a turn and add its rows to the log."""
        self._records.append(record)
        for row in log_rows(record):
            tags = [row.side.value]
            if row.problem:
                tags.append("problem")
            item = self.log.insert(
                "",
                "end",
                values=(
                    row.turn,
                    row.side.name.capitalize(),
                    row.action,
                    row.message,
                    row.thinking_ms,
                    row.problem,
                ),
                tags=tags,
            )
            self._rows_of_turn.setdefault(row.turn, []).append(item)
            self._jumps[item] = self._jump_callback(row.turn)

    def _jump_callback(self, turn: int) -> Callable[[], None]:
        """Show ``turn`` when its log row is selected."""

        def jump() -> None:
            if self.playback is not None:
                make_jump_to(self.playback, turn)()
                self._refresh()

        return jump

    def _refresh(self) -> None:
        """Draw the shown turn and update every control."""
        state = self.current_state()
        playback = self.playback
        if state is None or playback is None:
            return
        self.map_canvas.draw(state)
        self.score_label.configure(text=score_text(state))
        for side, label in self.status_labels.items():
            if side in state.players:
                status = player_status(state.player(side), self.rules)
                label.configure(text=f"{side.name.capitalize()}: {status}")
            else:
                label.configure(text="")
        self.turn_label.configure(text=playback.label)
        self.play_button.set_icon(
            IconName.PAUSE if playback.playing else IconName.PLAY
        )
        self._set_controls_enabled(True)
        self._moving_slider = True
        try:
            self.turn_slider.configure(to=max(1, playback.available))
            self.turn_slider.set(playback.current)
        finally:
            self._moving_slider = False
        self._highlight_turn(playback.current)

    def _highlight_turn(self, turn: int) -> None:
        """Mark the log rows of ``turn`` and scroll them into view."""
        for item in self.log.tag_has("current"):
            tags = self.log.item(item, "tags")
            self.log.item(item, tags=[tag for tag in tags if tag != "current"])
        rows = self._rows_of_turn.get(turn, [])
        for item in rows:
            tags = self.log.item(item, "tags")
            self.log.item(item, tags=[*tags, "current"])
        if rows:
            self.log.see(rows[0])

    def _set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable the playback buttons and the turn slider."""
        for button in self.buttons:
            button.set_enabled(enabled)
        self.turn_slider.state(["!disabled"] if enabled else ["disabled"])

    def _navigate(self, move: Callable[[Playback], None]) -> None:
        """Apply a playback move and redraw."""
        if self.playback is not None:
            move(self.playback)
            self._refresh()

    def _on_first(self) -> None:
        self._navigate(Playback.first)

    def _on_previous(self) -> None:
        self._navigate(Playback.previous)

    def _on_toggle(self) -> None:
        self._navigate(Playback.toggle)

    def _on_next(self) -> None:
        self._navigate(Playback.next)

    def _on_last(self) -> None:
        self._navigate(Playback.last)

    def _on_turn_slider(self, value: str) -> None:
        """The user moved the turn slider."""
        if self._moving_slider or self.playback is None:
            return
        turn = round(float(value))
        if turn != self.playback.current:
            self._navigate(lambda playback: playback.jump(turn))

    def _on_speed_slider(self, value: str) -> None:
        """The user changed the playback speed."""
        self._speed = round(float(value))

    def _on_log_select(self, _event: object) -> None:
        """Jump to the turn of the selected log row."""
        for item in self.log.selection():
            jump = self._jumps.get(item)
            if jump is not None:
                jump()

    def _schedule_tick(self) -> None:
        """Call :meth:`_on_tick` after one turn's time at the speed."""
        self._timer = self.after(tick_delay_ms(self._speed), self._on_tick)

    def _on_tick(self) -> None:
        """Move forward while playing, then wait for the next tick."""
        if self.playback is not None and self.playback.tick():
            self._refresh()
        elif self.playback is not None and not self.playback.playing:
            self.play_button.set_icon(IconName.PLAY)
        self._schedule_tick()

"""The History tab: every saved match, and the best solo results.

Matches can be sorted by clicking a column header, filtered by mode and
bot, opened in the viewer with a double click and deleted.
"""

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import Final

from arena.gui.history_table import (
    COLUMNS,
    bot_names,
    filter_summaries,
    history_row,
    solo_record_row,
    sort_summaries,
)
from arena.model.state import ModeKind
from arena.storage.records import MatchSummary, RecordedMatch
from arena.storage.repository import MatchRepository

ALL_MODES: Final = "All modes"
ALL_BOTS: Final = "All bots"
HEADINGS: Final = {
    "date": ("Date", 130),
    "mode": ("Mode", 60),
    "blue": ("Blue", 120),
    "red": ("Red", 120),
    "seed": ("Seed", 80),
    "result": ("Result", 170),
    "turns": ("Turns", 60),
}
RECORD_COLUMNS: Final = (
    ("seed", "Seed", 80),
    ("turns", "Best turns", 90),
    ("bot", "Bot", 140),
    ("date", "Date", 130),
)


class HistoryTab(ttk.Frame):
    """Lists the matches in the history and acts on the selected one."""

    def __init__(
        self,
        master: tk.Misc,
        repository: MatchRepository,
        on_open: Callable[[RecordedMatch], None],
        on_delete: Callable[[int], None],
    ) -> None:
        """Create the tab and show the history.

        Args:
            master: The parent widget.
            repository: The match history.
            on_open: Called with a loaded match to show it.
            on_delete: Called with the id of a deleted match.
        """
        super().__init__(master, padding=8)
        self.repository = repository
        self.on_open = on_open
        self.on_delete = on_delete
        self._sort_column = "date"
        self._descending = True
        self._ids: dict[str, int] = {}
        self._build_filters()
        self._build_table()
        self._build_records()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.refresh()

    def refresh(self) -> None:
        """Read the history again, keeping the sort order and filters."""
        summaries = self.repository.list_matches()
        self.bot_combo.configure(values=[ALL_BOTS, *bot_names(summaries)])
        if self.bot_combo.get() not in self.bot_combo.cget("values"):
            self.bot_combo.set(ALL_BOTS)
        shown = sort_summaries(
            filter_summaries(summaries, self._mode(), self._bot()),
            self._sort_column,
            self._descending,
        )
        self._fill_table(shown)
        self.records_table.delete(*self.records_table.get_children())
        for record in self.repository.solo_records():
            self.records_table.insert(
                "", "end", values=solo_record_row(record)
            )

    def sort_by(self, column: str) -> None:
        """Sort by ``column``; sorting by it again reverses the order."""
        if column == self._sort_column:
            self._descending = not self._descending
        else:
            self._sort_column, self._descending = column, False
        self.refresh()

    def open_selected(self) -> None:
        """Show the selected match in the viewer."""
        match_id = self._selected_id()
        if match_id is not None:
            self.on_open(self.repository.load_match(match_id))

    def delete_selected(self) -> None:
        """Delete the selected match after asking the user."""
        match_id = self._selected_id()
        if match_id is None:
            return
        if not messagebox.askyesno(
            "Delete match",
            "Delete the selected match from the history?",
            parent=self,
        ):
            return
        self.repository.delete_match(match_id)
        self.on_delete(match_id)
        self.refresh()

    def _build_filters(self) -> None:
        """The mode and bot filters and the buttons above the table."""
        bar = ttk.Frame(self)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(bar, text="Show").pack(side="left", padx=(0, 6))
        self.mode_combo = ttk.Combobox(
            bar,
            state="readonly",
            width=12,
            values=[
                ALL_MODES,
                *(mode.value.capitalize() for mode in ModeKind),
            ],
        )
        self.mode_combo.set(ALL_MODES)
        self.mode_combo.pack(side="left")
        self.bot_combo = ttk.Combobox(bar, state="readonly", width=20)
        self.bot_combo.set(ALL_BOTS)
        self.bot_combo.pack(side="left", padx=6)
        for combo in (self.mode_combo, self.bot_combo):
            combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        self.delete_button = ttk.Button(
            bar, text="Delete match", command=self.delete_selected
        )
        self.delete_button.pack(side="right")
        ttk.Button(bar, text="Open", command=self.open_selected).pack(
            side="right", padx=6
        )

    def _build_table(self) -> None:
        """The table of matches with sortable headers."""
        frame = ttk.Frame(self)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.table = ttk.Treeview(
            frame, columns=COLUMNS, show="headings", selectmode="browse"
        )
        for column in COLUMNS:
            heading, width = HEADINGS[column]
            self.table.heading(
                column, text=heading, command=self._make_sorter(column)
            )
            self.table.column(column, width=width, stretch=column == "result")
        scrollbar = ttk.Scrollbar(
            frame, orient="vertical", command=self.table.yview
        )
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.table.bind("<Double-1>", lambda _event: self.open_selected())
        self.table.bind("<Return>", lambda _event: self.open_selected())

    def _build_records(self) -> None:
        """The table of solo records under the matches."""
        ttk.Label(
            self, text="Solo records", font=("TkDefaultFont", 11, "bold")
        ).grid(row=2, column=0, sticky="w", pady=(12, 4))
        self.records_table = ttk.Treeview(
            self,
            columns=[name for name, _, _ in RECORD_COLUMNS],
            show="headings",
            height=5,
        )
        for name, heading, width in RECORD_COLUMNS:
            self.records_table.heading(name, text=heading)
            self.records_table.column(name, width=width, stretch=False)
        self.records_table.grid(row=3, column=0, sticky="ew")

    def _make_sorter(self, column: str) -> Callable[[], None]:
        """A header callback that sorts by ``column`` (a closure)."""

        def sort() -> None:
            self.sort_by(column)

        return sort

    def _fill_table(self, summaries: list[MatchSummary]) -> None:
        """Show ``summaries`` as the table's rows."""
        self.table.delete(*self.table.get_children())
        self._ids = {}
        for summary in summaries:
            item = self.table.insert("", "end", values=history_row(summary))
            if summary.match_id is not None:
                self._ids[item] = summary.match_id

    def _selected_id(self) -> int | None:
        """The id of the selected match, if any."""
        for item in self.table.selection():
            return self._ids.get(item)
        return None

    def _mode(self) -> ModeKind | None:
        """The mode filter; ``None`` for all modes."""
        chosen = self.mode_combo.get()
        return None if chosen == ALL_MODES else ModeKind(chosen.lower())

    def _bot(self) -> str | None:
        """The bot filter; ``None`` for all bots."""
        chosen = self.bot_combo.get()
        return None if chosen == ALL_BOTS else chosen

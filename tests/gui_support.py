"""A hidden tkinter root for widget tests.

Creating and destroying many ``Tk`` roots in one process makes ttk print
errors about destroyed applications, so all widget tests share one
withdrawn root and only their own widgets are destroyed after each test.
"""

import tkinter as tk
import unittest

_shared_roots: list[tk.Tk] = []


def hidden_root(test_case: unittest.TestCase) -> tk.Tk:
    """The shared withdrawn root; the test's widgets are removed after it.

    Skips the test when there is no display to open a window on.
    """
    if not _shared_roots:
        try:
            root = tk.Tk()
        except tk.TclError as error:
            message = f"no display for tkinter: {error}"
            raise unittest.SkipTest(message) from error
        root.withdraw()
        _shared_roots.append(root)
    root = _shared_roots[0]
    test_case.addCleanup(_remove_widgets, root)
    return root


def item_option(canvas: tk.Canvas, item: int, option: str) -> str:
    """One option of a canvas item, as text."""
    # Typeshed leaves Canvas.itemcget unannotated, so wrap it once here.
    return str(canvas.itemcget(item, option))  # type: ignore[no-untyped-call]


def _remove_widgets(root: tk.Tk) -> None:
    """Destroy every widget a test put on the root, and pending timers."""
    for child in root.winfo_children():
        child.destroy()
    for timer in root.tk.call("after", "info"):
        root.after_cancel(timer)
    root.update()

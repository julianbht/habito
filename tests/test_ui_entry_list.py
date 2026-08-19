"""EntryList on its own: the row list shared by all three manager dialogs.

What belongs here is the widget's own job — rendering rows, saying so when there are none,
and turning a gesture on a row into that row's index. What each dialog *does* with the
index is that dialog's own choice, tested where it lives.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QTreeWidget

from habito.ui.widgets.entry_list import EntryList


def list_for(qtbot, rows=(), hint="Right-click a row.", empty_text="Nothing here yet."):
    widget = EntryList(hint, empty_text)
    widget.set_rows(list(rows))
    qtbot.addWidget(widget)
    return widget


def row(widget, index):
    item = widget.tree.topLevelItem(index)
    assert item is not None  # the test already knows this row exists
    return item


def test_rows_are_listed_in_the_order_given(qtbot):
    widget = list_for(qtbot, ["first", "second"])

    assert widget.tree.topLevelItemCount() == 2
    assert row(widget, 0).text(0) == "first"
    assert row(widget, 1).text(0) == "second"


def test_an_empty_list_says_so_rather_than_showing_nothing(qtbot):
    widget = list_for(qtbot, [], empty_text="Nothing logged yet.")

    assert widget.empty_label.text() == "Nothing logged yet."


def test_the_empty_message_clears_once_there_are_rows(qtbot):
    widget = list_for(qtbot, [])

    widget.set_rows(["first"])

    assert widget.empty_label.text() == ""


def test_set_rows_replaces_rather_than_appends(qtbot):
    widget = list_for(qtbot, ["first", "second"])

    widget.set_rows(["only"])

    assert widget.tree.topLevelItemCount() == 1
    assert row(widget, 0).text(0) == "only"


def test_double_clicking_a_row_reports_its_index(qtbot):
    widget = list_for(qtbot, ["first", "second"])
    seen: list[int] = []
    widget.row_activated.connect(seen.append)

    widget.tree.itemDoubleClicked.emit(row(widget, 1), 0)

    assert seen == [1]


def test_a_context_menu_on_a_row_reports_its_index(qtbot):
    widget = list_for(qtbot, ["first", "second"])
    widget.show()
    qtbot.waitExposed(widget)
    seen: list[int] = []
    widget.row_menu_requested.connect(lambda index, _pos: seen.append(index))

    widget.tree.customContextMenuRequested.emit(widget.tree.visualItemRect(row(widget, 1)).center())

    assert seen == [1]


def test_a_context_menu_below_every_row_reports_nothing(qtbot):
    """Right-clicking the empty space under the last row must not resolve to a row —
    silently acting on the nearest one would be worse than doing nothing."""
    widget = list_for(qtbot, ["first"])
    widget.show()
    qtbot.waitExposed(widget)
    seen: list[int] = []
    widget.row_menu_requested.connect(lambda index, _pos: seen.append(index))

    widget.tree.customContextMenuRequested.emit(widget.tree.rect().bottomLeft())

    assert seen == []


def test_rows_are_not_editable_in_place(qtbot):
    """The log is append-only; a row is acted on through a dialog, never typed over."""
    widget = list_for(qtbot, ["first"])

    assert widget.tree.editTriggers() == QTreeWidget.EditTrigger.NoEditTriggers
    assert not (row(widget, 0).flags() & Qt.ItemFlag.ItemIsEditable)


def test_the_menu_position_is_global_so_a_dialog_can_pop_up_at_it(qtbot):
    """`row_menu_requested` hands over an already-mapped point, so no call site has to
    remember to map it itself."""
    widget = list_for(qtbot, ["first"])
    widget.show()
    qtbot.waitExposed(widget)
    seen: list[QPoint] = []
    widget.row_menu_requested.connect(lambda _index, pos: seen.append(pos))

    local = widget.tree.visualItemRect(row(widget, 0)).center()
    widget.tree.customContextMenuRequested.emit(local)

    assert seen == [widget.tree.viewport().mapToGlobal(local)]

"""A container widget whose background *is* the progress indicator.

Instead of a separate bar, the whole window fills left-to-right as the current phase
elapses, tinted toward that phase's colour. It's the window's outermost content widget so
the fill reaches every corner — including the row the ⚙ button sits in — rather than
stopping at the timer's edge.
"""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from habito.ui import theme


class ProgressBackground(QWidget):
    def __init__(self, ui_theme: theme.Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("progressBackground")
        self._theme = ui_theme
        self._fraction = 0.0
        self._fill = ui_theme.progress_fill(theme.OK)

    def set_progress(self, fraction: float, phase_color: str) -> None:
        """Set how far the fill reaches, repainting only when it would actually move."""
        fraction = max(0.0, min(1.0, fraction))
        fill = self._theme.progress_fill(phase_color)
        # Ticks are 250ms and the window is a few hundred px wide, so most ticks don't
        # move the edge by a whole pixel. Only repaint when they do.
        moved = round(fraction * self.width()) != round(self._fraction * self.width())
        if not moved and fill == self._fill:
            return
        self._fraction, self._fill = fraction, fill
        self.update()

    @property
    def fraction(self) -> float:
        return self._fraction

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        full = self.rect()
        painter.fillRect(full, self._theme.background())
        if self._fraction > 0:
            elapsed = QRect(full)
            elapsed.setWidth(round(full.width() * self._fraction))
            painter.fillRect(elapsed, self._fill)
        painter.end()
        super().paintEvent(event)

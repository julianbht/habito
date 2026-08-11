"""Local SVG icons — see icons/LICENSE.txt for provenance and license.

Colour is baked into each file rather than applied at paint time, unlike qtawesome. That
means these icons don't yet follow the light/dark palette or turn red in test mode.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

_DIR = Path(__file__).parent / "icons"


def icon(name: str) -> QIcon:
    return QIcon(str(_DIR / f"{name}.svg"))

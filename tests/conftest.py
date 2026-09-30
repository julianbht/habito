from __future__ import annotations

import os

from habito.config.models import SessionTemplate

# Render Qt widgets into an offscreen buffer so the UI tests need no display (and don't
# steal focus locally). Must be set before the first QApplication is created.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def make_config(work=25, brk=5, rounds=4) -> SessionTemplate:
    return SessionTemplate(work_minutes=work, break_minutes=brk, rounds=rounds)

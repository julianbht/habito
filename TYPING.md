# pyright / Pylance findings — history

`uv run pyright` — **0 errors**, down from 67. Split by what was actually wrong, because the
groups wanted different treatment and only one of them was "the library has no types".

Config lives in `pyproject.toml` under `[tool.pyright]`: `standard` everywhere,
`strict = ["src"]`.

**Don't blanket-disable a rule in `pyproject.toml`.** `reportUnknownMemberType` is what
caught `PomodoroEngine._emit` — 21 errors pointing at one untyped helper that let a typo'd
field name through. Turning the rule off for `src` would have hidden the bug along with
the noise.

---

## 0. Done — qtawesome (was 21 errors), then removed entirely

qtawesome ships no annotations, so `qta.icon(...)` came back `Unknown` and poisoned every
call it was passed into. `typings/qtawesome/__init__.pyi` described the one function this
project used, so `setIcon(qta.icon(...))` was genuinely checked rather than suppressed.

The dependency is now gone. Icons are vendored SVGs (`ui/icons/`, Google's Material
Symbols, Apache-2.0) loaded through `ui/svg_icons.py`'s `icon(name)`, which returns a plain
`QIcon` — already typed by PySide6's own stubs. `typings/qtawesome/` was deleted along with
it, exactly as this section predicted; there was no icon-typing work waiting on the other
side.

---

## 1. Done — PySide6's stubs are wrong about `None` (was 4 errors)

These accessors are typed as always returning a value. At runtime they return `None`, so
**the defensive checks are correct and were not deleted** — pyright was wrong, not the code.

| Where | Rule | The lie |
|---|---|---|
| `ui/phase_dialog.py:91` | `reportUnnecessaryComparison` | `windowHandle()` typed `QWindow`, returns `None` before the window is shown |
| `ui/phase_dialog.py:98` | `reportUnnecessaryComparison` | same |
| `ui/theme.py:87` | `reportUnnecessaryComparison` | `styleHints()` typed `QStyleHints`, returns `None` before a `QGuiApplication` exists |
| `ui/log_view.py:226` | `reportUnnecessaryComparison` | `QTreeWidgetItem.parent()` typed `QTreeWidgetItem`, returns `None` for a top-level item |

**Treatment:** inline `# pyright: ignore[reportUnnecessaryComparison]` with a short reason,
right on the line pyright flags — declaring the variable `X | None` doesn't help, because
pyright narrows the flow-sensitive type to the stub's (non-optional) return type at the
point of assignment regardless of the declared annotation. `theme.py`'s `palette_for` was
reshaped slightly (early-return on `None`) to keep the ignored line under the length limit;
behaviour is unchanged.

This was the one group where suppression was the right tool — it's specific, and the
comment is what stops someone deleting a check that looks dead and isn't. A config-level
disable would have let genuinely always-true conditions through everywhere else.

---

## 2. Done — PySide6's stubs don't model constructor kwargs (was 2 errors)

Qt accepts property and signal names as constructor keywords at runtime; the stubs only
declare the positional overloads.

| Where | Rule | Fix |
|---|---|---|
| `ui/app.py:136` | `reportCallIssue` | `QLabel(text, objectName="banner")`. The banner was redundant with the rest of test mode (red theme, "— TEST MODE" window title) and not needed as a warning, so it was **deleted** rather than fixed — along with its `QLabel#banner` stylesheet rule and the tests asserting it existed. |
| `ui/app.py:278` | `reportCallIssue` | `QShortcut(seq, self, activated=slot)` → construct then connect: `QShortcut(QKeySequence(keys), self).activated.connect(slot)`. The object stays alive the same way as before — parented to `self`. |

---

## 3. Done — genuinely local (was 7 errors)

Nothing to do with Qt's types. These were ours.

| Where | Rule | Fix |
|---|---|---|
| `ui/progress_background.py:33,49,49` | `reportUnknownMemberType` ×2, `reportUnknownArgumentType` | Annotated `self._fill: QColor` in `__init__`. Cleared all three. |
| `ui/log_view.py:104` | `reportUnnecessaryIsInstance` | `Event` is an exhaustive 10-member union; the preceding `elif` chain already excludes the other 9, so pyright narrows to `SessionRetracted` by elimination. Replaced the redundant `elif isinstance(...)` with `else:`. |
| `ui/log_view.py:214` | `reportOptionalMemberAccess` | `.setExpanded()` on a possibly-`None` item — real, unlike group 1. Assigned `topLevelItem(0)` to a variable and guarded with `is not None`. |
| `app.py:63` | `reportArgumentType` | `QApplication.instance()` returns `QCoreApplication \| QApplication`. Narrowed with `isinstance` before `theme.apply()`. |
| `evidence/worker.py:87` | `reportArgumentType` | The queue held events *and* the `_SENTINEL`/`_FLUSH` markers, typed as `object`. Replaced the two bare `object()` sentinels with a 2-member `_Signal` enum and typed the queue `Queue[Event \| _Signal]`, so excluding both members by elimination narrows `_process(item)` to a real `Event`. |

---

## 4. Done — tests (was 12 errors)

`standard` mode, not `strict`. All of them were tests reaching past a public API on purpose;
none said anything about whether the app worked.

| Where | Rule | Fix |
|---|---|---|
| `tests/test_ui_sounds.py:124,125,133` | `reportOptionalMemberAccess` | `assert x is not None` before reading `.sound` off the recorded call |
| `tests/test_ui_sounds.py:146,147` | `reportAttributeAccessIssue` ×2 | inline `# pyright: ignore[reportAttributeAccessIssue]` — `DesktopNotifier.__new__` deliberately bypasses `__init__` |
| `tests/test_ui_calendar.py:53,95,114` | `reportIndexIssue` | `QColor.getRgb()` is stubbed `-> object`; use `.red()/.green()/.blue()` (each typed `int`) instead of indexing it |
| `tests/test_timezone.py:151,164` | `reportArgumentType` | added a minimal `_NoopController` satisfying the `Controller` protocol, in place of `controller=None` |
| `tests/test_timezone.py:60` | `reportOptionalMemberAccess` | `assert offset is not None` before `.total_seconds()` |
| `tests/test_ui_notifications.py:163` | `reportAttributeAccessIssue` | `assert isinstance(window._notifier, DesktopNotifier)` — same narrowing pattern already used in `ui/app.py` |

---

## Remaining

Nothing — `uv run pyright` is clean across `src` and `tests`.

"""The settings panel, generated from `Options` (UC-08).

No widget is written out by hand: every control comes from a field's declared
metadata, exactly as the argparse parser does. That is what makes CLI/GUI parity
structural — adding an option puts it in both front ends at once.
"""
from __future__ import annotations

from dataclasses import fields
from typing import Callable

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..settings import Options

#: Where remembered settings live. A user with a habitual margin sets it once.
ORGANISATION = "eco-print"
APPLICATION = "eco-print"


def default_store() -> QSettings:
    """Where the application keeps its remembered settings."""
    return QSettings(ORGANISATION, APPLICATION)


def load_remembered(
    defaults: Options | None = None, store: QSettings | None = None
) -> Options:
    """The settings from the last session, falling back to the defaults.

    Only settings are remembered — never inputs or crops, which belong to one
    job rather than to the user's habits (UC-08). `store` is injectable so tests
    need not touch the real preferences of the machine they run on.
    """
    stored = store or default_store()
    values = {}
    for field in fields(Options):
        default = getattr(defaults or Options(), field.name)
        raw = stored.value(f"options/{field.name}", None)
        if raw is None:
            values[field.name] = default
            continue
        try:
            values[field.name] = _coerce(field, raw)
        except (TypeError, ValueError):
            values[field.name] = default
    return Options(**values)


def remember(options: Options, store: QSettings | None = None) -> None:
    """Store settings for the next session."""
    stored = store or default_store()
    for field in fields(Options):
        stored.setValue(f"options/{field.name}", getattr(options, field.name))


def _coerce(field, raw):
    """QSettings hands back strings on some platforms; restore the real type."""
    kind = field.metadata["control"]
    if kind == "check":
        if isinstance(raw, str):
            return raw.lower() in ("true", "1", "yes")
        return bool(raw)
    if kind == "combo":
        value = str(raw)
        if value not in field.metadata["choices"]:
            raise ValueError(value)
        return value
    value = float(raw)
    if not field.metadata["minimum"] <= value <= field.metadata["maximum"]:
        raise ValueError(value)
    return value


def control_for(field, value):
    """Build the widget a field's metadata asks for."""
    meta = field.metadata
    kind = meta["control"]

    if kind == "check":
        widget = QCheckBox(meta["label"])
        widget.setChecked(bool(value))
    elif kind == "combo":
        widget = QComboBox()
        widget.addItems([choice.upper() for choice in meta["choices"]])
        widget.setCurrentIndex(list(meta["choices"]).index(value))
    else:
        widget = QDoubleSpinBox()
        widget.setRange(meta["minimum"], meta["maximum"])
        widget.setValue(float(value))
        widget.setDecimals(1)
        widget.setSingleStep(2.0)
        if meta["unit"]:
            widget.setSuffix(f" {meta['unit']}")

    widget.setToolTip(f"{meta['help']}  ({meta['flag']})")
    return widget


def value_of(field, widget):
    """Read a widget back into the field's type."""
    kind = field.metadata["control"]
    if kind == "check":
        return widget.isChecked()
    if kind == "combo":
        return field.metadata["choices"][widget.currentIndex()]
    return float(widget.value())


class SettingsPanel(QGroupBox):
    """Every option, in a block that starts collapsed unless it has something
    to show (UC-03).

    The tool must be usable by dropping files and pressing save without reading
    anything, so a user on the defaults never sees the options unasked. But a
    user who arrives with a non-default setting -- typically one remembered
    from a previous session -- has already told the tool it matters to them,
    so the panel opens by itself rather than hiding an active setting.
    """

    def __init__(self, options: Options, on_change: Callable[[Options], None]):
        super().__init__("Settings")
        self._on_change = on_change
        self._widgets: dict[str, QWidget] = {}
        self._suspended = False

        self.setCheckable(True)
        self.setChecked(options != Options())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # All body content lives in one container widget, toggled as a single
        # unit (see `_set_body_visible`) rather than each control being shown
        # or hidden individually.
        self._body = QWidget(self)
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(9, 9, 9, 9)
        form = QFormLayout()
        checks = QVBoxLayout()

        for field in fields(Options):
            widget = control_for(field, getattr(options, field.name))
            self._widgets[field.name] = widget
            self._connect(field, widget)
            if field.metadata["control"] == "check":
                checks.addWidget(widget)
            else:
                form.addRow(f"{field.metadata['label']}:", widget)

        body_layout.addLayout(form)
        body_layout.addLayout(checks)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        reset = QPushButton("Reset to defaults")
        reset.clicked.connect(self.reset)
        buttons.addWidget(reset)
        body_layout.addLayout(buttons)

        outer.addWidget(self._body)

        self.toggled.connect(self._on_toggle)
        self._set_body_visible(self.isChecked())

    def _connect(self, field, widget) -> None:
        signal = {
            "check": lambda w: w.toggled,
            "combo": lambda w: w.currentIndexChanged,
            "spin": lambda w: w.valueChanged,
        }[field.metadata["control"]](widget)
        signal.connect(self._emit)

    def _on_toggle(self, checked: bool) -> None:
        self._set_body_visible(checked)

    def _set_body_visible(self, visible: bool) -> None:
        """Show or hide every control as one unit, and force the resulting
        layout change to settle immediately.

        Toggling ~15 individual child widgets one by one (the previous
        approach) left a window where the group box had grown to its new
        size but the platform's hit-testing for the freshly shown controls
        had not yet caught up with it — the first real click after expanding
        the panel landed on stale geometry and was lost, so a control needed
        two clicks: one that appeared to do nothing, one that worked. Toggling
        a single container and immediately re-activating this widget's layout
        (rather than waiting for the next event-loop iteration to do it)
        closes that window.
        """
        self._body.setVisible(visible)
        self.layout().invalidate()
        self.layout().activate()
        window_layout = self.window().layout() if self.window() is not None else None
        if window_layout is not None:
            window_layout.activate()

    def options(self) -> Options:
        """The settings the panel currently describes."""
        return Options(**{
            f.name: value_of(f, self._widgets[f.name]) for f in fields(Options)
        })

    def set_options(self, options: Options) -> None:
        """Show `options` without emitting a change for each widget."""
        self._suspended = True
        try:
            for field in fields(Options):
                widget = self._widgets[field.name]
                value = getattr(options, field.name)
                kind = field.metadata["control"]
                if kind == "check":
                    widget.setChecked(bool(value))
                elif kind == "combo":
                    widget.setCurrentIndex(list(field.metadata["choices"]).index(value))
                else:
                    widget.setValue(float(value))
        finally:
            self._suspended = False
        self._emit()

    def reset(self) -> None:
        self.set_options(Options())

    def _emit(self, *_ignored) -> None:
        if not self._suspended:
            self._on_change(self.options())

"""UC-08: every option is reachable from both front ends.

Parity by discipline fails the first time an option is added, so it is asserted
structurally instead: these tests walk the fields of `Options` and demand that
each one can be set from the command line and drawn in the GUI panel. Adding a
field without wiring it up fails the suite rather than shipping.

The GUI half is checked twice: against the *declaration* each widget is built
from, and — when the GUI extra is installed — against the built panel itself, so
a field cannot be declared correctly yet fail to appear on screen.
"""
from __future__ import annotations

import argparse
from dataclasses import fields

import pytest

from eco_print.settings import GUI_BEHAVIOUR_FLAGS, Options, add_options


def parse(argv: list[str]) -> Options:
    parser = add_options(argparse.ArgumentParser())
    return Options.from_namespace(parser.parse_args(argv))


def sample_value(f) -> tuple[list[str], object]:
    """A command line that changes `f`, and the value it should produce."""
    meta = f.metadata
    if meta["control"] == "check":
        return [meta["flag"]], True
    if meta["control"] == "combo":
        other = [c for c in meta["choices"] if c != f.default][0]
        return [meta["flag"], other], other
    value = float(f.default) + 5
    return [meta["flag"], str(value)], value


class TestCliHalf:
    def test_every_option_has_a_flag(self):
        for f in fields(Options):
            assert f.metadata.get("flag"), f"{f.name} has no CLI flag"

    def test_every_option_is_settable_from_the_command_line(self):
        for f in fields(Options):
            argv, expected = sample_value(f)
            assert getattr(parse(argv), f.name) == expected, f"{f.name} not settable"

    def test_every_option_appears_in_the_help(self):
        parser = add_options(argparse.ArgumentParser())
        help_text = parser.format_help()
        for f in fields(Options):
            assert f.metadata["flag"] in help_text, f"{f.name} missing from --help"


class TestGuiHalf:
    def test_every_option_declares_a_control(self):
        for f in fields(Options):
            assert f.metadata.get("control") in ("spin", "check", "combo"), (
                f"{f.name} declares no GUI control"
            )

    def test_every_option_has_wording_for_a_widget(self):
        """A flag reads as an instruction; a checkbox reads as a state."""
        for f in fields(Options):
            assert f.metadata.get("label"), f"{f.name} has no GUI label"

    def test_numeric_controls_declare_their_range(self):
        """A spin box cannot be drawn without bounds."""
        for f in fields(Options):
            if f.metadata["control"] == "spin":
                assert f.metadata["minimum"] is not None, f"{f.name} has no minimum"
                assert f.metadata["maximum"] is not None, f"{f.name} has no maximum"

    def test_choice_controls_declare_their_choices(self):
        for f in fields(Options):
            if f.metadata["control"] == "combo":
                assert f.metadata["choices"], f"{f.name} has no choices"


class TestExceptions:
    def test_the_excused_list_is_closed(self):
        """Exactly three flags are satisfied by GUI behaviour, not a control.

        This assertion exists so that excusing a fourth is a deliberate act —
        editing this list and UC-08 — rather than a quiet omission.
        """
        assert GUI_BEHAVIOUR_FLAGS == ("--force", "--dry-run", "output path")

    def test_no_excused_flag_is_also_an_option(self):
        flags = {f.metadata["flag"] for f in fields(Options)}
        assert flags.isdisjoint(GUI_BEHAVIOUR_FLAGS)


class TestGuiPanelItself:
    """The GUI half, asserted against the built panel rather than the metadata.

    Skipped when the GUI extra is not installed — the CLI must remain testable
    without Qt.
    """

    @pytest.fixture
    def panel(self):
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PySide6", reason="the GUI extra is not installed")
        from PySide6.QtWidgets import QApplication

        from eco_print.gui.settings_panel import SettingsPanel

        QApplication.instance() or QApplication([])
        return SettingsPanel(Options(), lambda options: None)

    def test_every_option_is_present_in_the_panel(self, panel):
        assert {f.name for f in fields(Options)} == set(panel._widgets)

    def test_every_option_can_be_changed_through_the_panel(self, panel):
        """The mirror of the CLI test above: no field is unreachable by hand."""
        for f in fields(Options):
            changed = _toggle(panel, f)
            assert getattr(panel.options(), f.name) == changed, (
                f"{f.name} cannot be set from the panel"
            )
        panel.reset()


def _toggle(panel, f):
    """Move one widget off its default and return the value it now holds."""
    widget = panel._widgets[f.name]
    kind = f.metadata["control"]
    if kind == "check":
        widget.setChecked(not widget.isChecked())
        return widget.isChecked()
    if kind == "combo":
        other = [c for c in f.metadata["choices"] if c != f.default][0]
        widget.setCurrentIndex(list(f.metadata["choices"]).index(other))
        return other
    widget.setValue(float(f.default) + 5)
    return float(f.default) + 5

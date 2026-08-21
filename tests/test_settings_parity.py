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


class TestEffectsAreReal:
    """UC-08: reachability is not the whole requirement.

    A widget that changes `Options` but that nothing downstream reads is
    reachable and useless at once — exactly the shape `verbose` took in the
    GUI before the Details pane existed to consume it (M6 -> M7). Each option
    here is exercised against the stage it is documented to affect, and the
    assertion is that the stage's *output* differs, not merely that `Options`
    itself does.
    """

    #: field name -> the stage it is documented to affect (UC-08's mapping table)
    STAGES = {
        "margin": "packing",
        "gap": "packing",
        "pad": "detection",
        "page_size": "composition",
        "full_ink": "detection",
        "separator": "composition",
        "reorder": "packing",
        "recursive": "loading",
        "verbose": "view",
    }

    def test_every_option_has_a_documented_stage(self):
        """A new field with no entry here has not been checked at all."""
        assert set(self.STAGES) == {f.name for f in fields(Options)}

    def test_every_stage_actually_appears(self):
        """Catches a typo'd stage name silently going unexercised below."""
        exercised = {
            name[len("test_"):].split("_changes_")[-1]
            for name in dir(self)
            if name.startswith("test_") and "_changes_" in name
        }
        assert set(self.STAGES.values()) <= exercised

    # -- detection ------------------------------------------------------

    def test_pad_changes_detection(self, data_dir: Path):
        from eco_print.detect import detect
        from eco_print.loader import load_pages

        page = load_pages([data_dir / "statement-a.pdf"]).pages[0]
        tight = detect(page, Options(pad=0.0))
        padded = detect(page, Options(pad=30.0))
        assert padded.box.height > tight.box.height

    def test_full_ink_changes_detection(self, data_dir: Path):
        from eco_print.detect import detect
        from eco_print.loader import load_pages

        page = load_pages([data_dir / "with-footer.pdf"]).pages[0]
        default = detect(page, Options())
        kept = detect(page, Options(full_ink=True))
        assert kept.box.height > default.box.height
        assert kept.method == "full-ink"

    # -- packing ----------------------------------------------------------

    def test_margin_changes_packing(self, blocks_from):
        from eco_print.packer import pack_ordered

        blocks = blocks_from([f"statement-{n}" for n in "abcde"])
        wide_margin = pack_ordered(blocks, Options(margin=200.0))
        narrow_margin = pack_ordered(blocks, Options(margin=5.0))
        assert wide_margin.sheet_count >= narrow_margin.sheet_count
        assert wide_margin.sheet_count > 2  # tight enough to force a difference

    def test_gap_changes_packing(self, make_block):
        from eco_print.packer import pack_ordered

        usable = Options().usable_height()
        blocks = [make_block(usable / 2), make_block(usable / 2)]
        tight = pack_ordered(blocks, Options(gap=0.0))
        loose = pack_ordered(blocks, Options(gap=40.0))
        assert tight.sheet_count < loose.sheet_count

    def test_reorder_changes_packing(self, blocks_from):
        from eco_print.packer import pack

        blocks = blocks_from([f"packing-{n}" for n in "abc"])
        ordered = pack(blocks, Options(reorder=False))
        reordered = pack(blocks, Options(reorder=True))
        assert reordered.sheet_count < ordered.sheet_count

    # -- composition --------------------------------------------------------

    def test_page_size_changes_composition(self, blocks_from, tmp_path: Path):
        from eco_print.compose import write
        from eco_print.packer import pack_ordered
        from pypdf import PdfReader

        blocks = blocks_from(["statement-a"])
        for size, expected_width in (("a4", 595.275), ("letter", 612.0)):
            options = Options(page_size=size)
            output = tmp_path / f"{size}.pdf"
            write(pack_ordered(blocks, options), output, options)
            width = float(PdfReader(str(output)).pages[0].mediabox.width)
            assert width == pytest.approx(expected_width)

    def test_separator_changes_composition(self, blocks_from, tmp_path: Path):
        from eco_print.compose import write
        from eco_print.detect import WHITE_THRESHOLD
        from eco_print.packer import pack_ordered

        def ink_count(path):
            import numpy as np
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(str(path))
            try:
                raster = np.asarray(
                    document[0].render(scale=1.0, grayscale=True).to_pil().convert("L")
                )
            finally:
                document.close()
            return int((raster < WHITE_THRESHOLD).sum())

        blocks = blocks_from(["statement-a", "statement-b"])
        plain = tmp_path / "plain.pdf"
        ruled = tmp_path / "ruled.pdf"
        write(pack_ordered(blocks, Options()), plain, Options())
        write(pack_ordered(blocks, Options(separator=True)), ruled, Options(separator=True))
        assert ink_count(ruled) > ink_count(plain)

    # -- loading --------------------------------------------------------------

    def test_recursive_changes_loading(self, statement_dir: Path, data_dir: Path):
        import shutil

        from eco_print.loader import expand_inputs

        nested = statement_dir / "more"
        nested.mkdir()
        shutil.copy(data_dir / "landscape.pdf", nested / "landscape.pdf")

        shallow = expand_inputs([statement_dir])
        deep = expand_inputs([statement_dir], recursive=True)
        assert len(deep) > len(shallow)

    # -- view -----------------------------------------------------------------

    def test_verbose_changes_view(self, statement_dir: Path, tmp_path: Path, capsys):
        from eco_print.cli import main

        output_a = tmp_path / "quiet.pdf"
        main([str(statement_dir), str(output_a)])
        quiet = capsys.readouterr().out

        output_b = tmp_path / "loud.pdf"
        main([str(statement_dir), str(output_b), "-v"])
        loud = capsys.readouterr().out

        assert "statement-a.pdf p1" not in quiet
        assert "statement-a.pdf p1" in loud

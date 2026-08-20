"""The Qt layer (UC-03, UC-04, UC-08).

Only glue lives in the widgets, so these tests are few and shallow: that the
panel really is generated from `Options`, that the window reflects the session,
and that the parity requirement holds against the actual panel rather than
against the declaration alone.

Runs offscreen; no display server is needed. Skipped entirely when PySide6 is
not installed, since the GUI is an optional extra.
"""
from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6", reason="the GUI extra is not installed")

from PySide6.QtWidgets import QApplication  # noqa: E402

from eco_print.gui.app import MainWindow  # noqa: E402
from eco_print.gui.settings_panel import SettingsPanel  # noqa: E402
from eco_print.settings import Options  # noqa: E402

STATEMENTS = [f"statement-{n}" for n in "abcde"]


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qt_app, data_dir: Path, tmp_path: Path):
    """A window backed by a throwaway settings store.

    Without this the suite would read the developer's own saved settings, and a
    remembered `--reorder` would quietly change what these tests assert.
    """
    from PySide6.QtCore import QSettings

    def build(stems: list[str] = ()) -> MainWindow:
        paths = [str(data_dir / f"{stem}.pdf") for stem in stems]
        store = QSettings(str(tmp_path / "window.ini"), QSettings.IniFormat)
        return MainWindow(paths, store=store)

    return build


class TestSettingsPanelIsGenerated:
    def test_every_option_gets_a_widget(self, qt_app):
        """UC-08, the GUI half — asserted against the built panel."""
        panel = SettingsPanel(Options(), lambda options: None)
        assert {f.name for f in fields(Options)} == set(panel._widgets)

    def test_each_widget_matches_its_declared_kind(self, qt_app):
        from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox

        expected = {"check": QCheckBox, "combo": QComboBox, "spin": QDoubleSpinBox}
        panel = SettingsPanel(Options(), lambda options: None)
        for field in fields(Options):
            assert isinstance(
                panel._widgets[field.name], expected[field.metadata["control"]]
            )

    def test_a_widget_change_reports_new_options(self, qt_app):
        seen = []
        panel = SettingsPanel(Options(), seen.append)
        panel._widgets["reorder"].setChecked(True)
        assert seen[-1].reorder is True

    def test_the_panel_round_trips_its_options(self, qt_app):
        panel = SettingsPanel(Options(), lambda options: None)
        wanted = Options(margin=10.0, gap=33.5, page_size="letter", separator=True)
        panel.set_options(wanted)
        assert panel.options() == wanted

    def test_reset_restores_the_defaults(self, qt_app):
        panel = SettingsPanel(Options(), lambda options: None)
        panel.set_options(Options(gap=99.0))
        panel.reset()
        assert panel.options() == Options()

    def test_the_panel_starts_collapsed(self, qt_app):
        """Dropping files and pressing save must need no reading (UC-03)."""
        assert SettingsPanel(Options(), lambda options: None).isChecked() is False

    def test_a_tooltip_names_the_equivalent_flag(self, qt_app):
        panel = SettingsPanel(Options(), lambda options: None)
        assert "--reorder" in panel._widgets["reorder"].toolTip()


class TestWindow:
    def test_dropping_documents_fills_the_list(self, window):
        w = window(STATEMENTS)
        assert w.list.count() == 5
        assert "2 pages" in w.status.text()

    def test_saving_is_disabled_until_there_is_something_to_save(self, window):
        assert window().save.isEnabled() is False
        assert window(["statement-a"]).save.isEnabled() is True

    def test_a_row_shows_its_height(self, window):
        assert "163 pt" in window(["statement-a"]).list.item(0).text()

    def test_a_manual_crop_is_marked_in_the_list(self, window):
        w = window(["statement-a"])
        w.session.set_manual_box(0, 800.0, 400.0)
        w._rebuild_rows()
        assert "✎" in w.list.item(0).text()

    def test_a_blank_page_is_listed_as_skipped(self, window):
        assert "blank" in window(["blank"]).list.item(0).text()

    def test_removing_a_row_updates_the_status(self, window):
        w = window(STATEMENTS)
        w.list.setCurrentRow(0)
        w._remove_selected()
        assert w.list.count() == 4

    def test_settings_are_remembered_for_the_next_session(self, window, tmp_path):
        """UC-08: a user with a habitual margin sets it once."""
        from PySide6.QtCore import QSettings

        from eco_print.gui.settings_panel import load_remembered

        w = window(["statement-a"])
        w.settings._widgets["reorder"].setChecked(True)
        reopened = QSettings(str(tmp_path / "window.ini"), QSettings.IniFormat)
        assert load_remembered(store=reopened).reorder is True

    def test_a_settings_change_reaches_the_session(self, window):
        w = window(["with-footer"])
        w.settings._widgets["full_ink"].setChecked(True)
        assert w.session.options.full_ink is True
        assert w.session.entries[0].height > 700

    def test_the_status_line_follows_the_settings(self, window):
        w = window([f"packing-{n}" for n in "abc"])
        assert "3 pages" in w.status.text()
        w.settings._widgets["reorder"].setChecked(True)
        assert "2 pages" in w.status.text()

    def test_saving_writes_the_document(self, window, tmp_path: Path, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
        w = window(STATEMENTS)
        target = tmp_path / "out.pdf"
        w.output.setText(str(target))
        w._save()

        from pypdf import PdfReader

        assert len(PdfReader(str(target)).pages) == 2

    def test_copying_the_command_line_puts_it_on_the_clipboard(self, window, qt_app):
        from PySide6.QtGui import QGuiApplication

        w = window(["statement-a"])
        w._copy_command_line()
        assert "eco-print" in QGuiApplication.clipboard().text()


class TestCropView:
    def test_the_view_reports_a_drag_in_pdf_coordinates(self, qt_app, data_dir: Path):
        from eco_print.gui.cropview import CropView
        from eco_print.loader import load_pages

        reported = []
        view = CropView(lambda top, bottom: reported.append((top, bottom)))
        page = load_pages([data_dir / "statement-a.pdf"]).pages[0]
        view.show_page(page, top=800.0, bottom=600.0)
        view._dragging = "bottom"
        view._bottom = 300.0            # points from the page top
        view._emit()

        top, bottom = reported[-1]
        assert top == pytest.approx(800.0)
        assert bottom == pytest.approx(page.height - 300.0)

    def test_edges_snap_to_ink_boundaries(self, qt_app, data_dir: Path):
        """UC-04: a clean cut between paragraphs needs no precision."""
        from eco_print.gui.cropview import CropView
        from eco_print.loader import load_pages

        view = CropView(lambda top, bottom: None)
        page = load_pages([data_dir / "statement-a.pdf"]).pages[0]
        view.show_page(page, top=page.height, bottom=0.0)
        assert view._snap(38.0) == pytest.approx(40.0, abs=1)

    def test_the_view_actually_paints(self, qt_app, data_dir: Path):
        """Painting is only exercised by painting: a signature error here is
        invisible to every other test in this file."""
        from PySide6.QtGui import QPixmap

        from eco_print.gui.cropview import CropView
        from eco_print.loader import load_pages

        view = CropView(lambda top, bottom: None)
        page = load_pages([data_dir / "statement-a.pdf"]).pages[0]
        view.show_page(page, top=800.0, bottom=600.0)
        view.resize(300, 400)

        canvas = QPixmap(300, 400)
        view.render(canvas)
        assert not canvas.isNull()

    def test_an_empty_view_paints_its_placeholder(self, qt_app):
        from PySide6.QtGui import QPixmap

        from eco_print.gui.cropview import CropView

        view = CropView(lambda top, bottom: None)
        view.resize(200, 200)
        canvas = QPixmap(200, 200)
        view.render(canvas)
        assert not canvas.isNull()

    def test_a_far_edge_does_not_snap(self, qt_app, data_dir: Path):
        from eco_print.gui.cropview import CropView
        from eco_print.loader import load_pages

        view = CropView(lambda top, bottom: None)
        page = load_pages([data_dir / "statement-a.pdf"]).pages[0]
        view.show_page(page, top=page.height, bottom=0.0)
        assert view._snap(400.0) == 400.0


class TestRememberedSettings:
    """UC-08: settings persist between sessions; inputs and crops do not.

    Each test gets its own ini file, so the suite never reads or writes the
    preferences of the machine it runs on.
    """

    @pytest.fixture
    def store(self, qt_app, tmp_path):
        from PySide6.QtCore import QSettings

        return QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    def test_nothing_stored_gives_the_defaults(self, store):
        from eco_print.gui.settings_panel import load_remembered

        assert load_remembered(store=store) == Options()

    def test_settings_survive_a_round_trip(self, store):
        from eco_print.gui.settings_panel import load_remembered, remember

        wanted = Options(margin=12.0, gap=44.0, page_size="letter", reorder=True)
        remember(wanted, store=store)
        assert load_remembered(store=store) == wanted

    def test_a_corrupt_stored_value_falls_back_to_the_default(self, store):
        from eco_print.gui.settings_panel import load_remembered

        store.setValue("options/margin", "not a number")
        store.setValue("options/page_size", "papyrus")
        restored = load_remembered(store=store)
        assert restored.margin == Options().margin
        assert restored.page_size == Options().page_size

    def test_an_out_of_range_value_is_rejected(self, store):
        from eco_print.gui.settings_panel import load_remembered

        store.setValue("options/margin", 99999)
        assert load_remembered(store=store).margin == Options().margin

    def test_a_boolean_survives_being_stored_as_text(self, store):
        """QSettings hands values back as strings on some platforms."""
        from eco_print.gui.settings_panel import load_remembered

        store.setValue("options/reorder", "true")
        assert load_remembered(store=store).reorder is True

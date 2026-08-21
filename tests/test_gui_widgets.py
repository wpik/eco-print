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

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

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

    def test_one_click_after_expanding_is_enough_to_toggle_a_control(
        self, qt_app
    ):
        """Regression check for the reported "need to click twice" bug.

        Honest limitation: this could not be made to reproduce the reported
        symptom on the offscreen test backend at all -- not even the pre-fix
        code (~15 widgets shown individually via findChildren, no forced
        layout pass) failed this test once the click targeted the checkbox's
        real content rather than QTest's default widget-centre position
        (which lands in blank stretched space for a wide row and proves
        nothing either way). The offscreen QPA platform evidently settles
        layouts synchronously in a way the real platform backend may not.
        This test therefore pins the intended behaviour -- one click after
        expanding is enough -- without claiming to prove the underlying
        platform race is fixed; that needs confirming on a real display.
        """
        panel = SettingsPanel(Options(), lambda options: None)
        panel.resize(1000, 10)   # wide enough that a centre-click would miss
        panel.show()
        qt_app.processEvents()

        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest

        panel.setChecked(True)
        widget = panel._widgets["reorder"]
        assert widget.isVisible() and widget.isEnabled()

        # Click within the checkbox's real content (its sizeHint), not the
        # centre of the row it has been stretched to fill.
        QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10))
        assert panel.options().reorder is True

    def test_expanding_toggles_a_single_container_not_each_control(self, qt_app):
        """The bug's likely mechanism: ~15 individual setVisible() calls left
        a window where the panel had grown but a freshly shown control's
        click-hit-region had not caught up. Toggling one container instead of
        each control individually removes that surface area; this test pins
        that structural choice so a future change cannot silently reintroduce
        the fragile pattern."""
        panel = SettingsPanel(Options(), lambda options: None)
        assert hasattr(panel, "_body")
        for widget in panel._widgets.values():
            assert panel._body.isAncestorOf(widget)

    def test_expanding_forces_a_synchronous_layout_pass(self, qt_app):
        """Geometry must be final by the time _set_body_visible returns --
        not deferred to the next event-loop iteration, which is exactly the
        kind of gap real click timing could fall into on some platforms even
        though it did not reproduce on the offscreen test backend."""
        panel = SettingsPanel(Options(), lambda options: None)
        panel.resize(400, 10)
        panel.show()
        qt_app.processEvents()

        panel.setChecked(True)
        size_immediately = panel._widgets["reorder"].size()
        qt_app.processEvents()
        size_after_extra_pump = panel._widgets["reorder"].size()

        assert size_immediately == size_after_extra_pump
        assert size_immediately.height() > 0
        assert size_immediately.width() > 0

    def test_the_panel_starts_collapsed_on_defaults(self, qt_app):
        """Dropping files and pressing save must need no reading (UC-03)."""
        assert SettingsPanel(Options(), lambda options: None).isChecked() is False

    def test_the_panel_starts_expanded_on_a_non_default_setting(self, qt_app):
        """A non-default setting -- typically one remembered from a previous
        session -- has already told the tool it matters; hiding it behind a
        click would be a worse default than showing it."""
        panel = SettingsPanel(Options(reorder=True), lambda options: None)
        assert panel.isChecked() is True

    def test_an_expanded_panel_actually_shows_its_widgets(self, qt_app):
        """Regression: checked state alone is not enough -- the body widgets
        must actually be told to show themselves too."""
        panel = SettingsPanel(Options(gap=99.0), lambda options: None)
        panel.show()
        qt_app.processEvents()
        assert panel._widgets["gap"].isVisible()

    def test_a_single_non_default_field_is_enough_to_expand(self, qt_app):
        panel = SettingsPanel(Options(separator=True), lambda options: None)
        assert panel.isChecked() is True

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

    def test_a_remembered_non_default_setting_expands_the_panel_on_open(
        self, qt_app, tmp_path: Path
    ):
        """The real path: settings saved by a previous session, read back by
        the next one -- not just SettingsPanel built directly with a value."""
        from PySide6.QtCore import QSettings

        from eco_print.gui.settings_panel import remember
        from eco_print.settings import Options

        store = QSettings(str(tmp_path / "remembered.ini"), QSettings.IniFormat)
        remember(Options(margin=50.0), store=store)

        w = MainWindow([], store=store)
        assert w.settings.isChecked() is True

    def test_all_default_remembered_settings_leave_the_panel_collapsed(
        self, qt_app, tmp_path: Path
    ):
        from PySide6.QtCore import QSettings

        store = QSettings(str(tmp_path / "remembered.ini"), QSettings.IniFormat)
        w = MainWindow([], store=store)
        assert w.settings.isChecked() is False

    def test_copy_save_exit_share_one_row_in_that_order(self, window, qt_app):
        """Per explicit request: Copy, Save (default), Exit, left to right,
        all on one row."""
        w = window(["statement-a"])
        w.show()
        qt_app.processEvents()

        copy = _find_button(w, "Copy as command line")
        assert copy is not None

        copy_pos = copy.mapTo(w, copy.rect().topLeft())
        save_pos = w.save.mapTo(w, w.save.rect().topLeft())
        exit_pos = w.exit_button.mapTo(w, w.exit_button.rect().topLeft())

        assert copy_pos.y() == save_pos.y() == exit_pos.y()
        assert copy_pos.x() < save_pos.x() < exit_pos.x()

    def test_save_is_the_only_default_button(self, window):
        """UC-03: Save PDF alone is marked default (and so, on macOS,
        rendered blue); Copy and Exit must never borrow that role, even via
        keyboard focus."""
        w = window(["statement-a"])
        copy = _find_button(w, "Copy as command line")

        assert w.save.isDefault() is True
        assert copy.isDefault() is False
        assert w.exit_button.isDefault() is False

        assert copy.autoDefault() is False
        assert w.exit_button.autoDefault() is False

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
        monkeypatch.setattr(QMessageBox, "exec", lambda self: None)
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


class TestReorderOffer:
    """Save PDF may ask, before writing, whether to enable minimise-pages
    (#12). QMessageBox.exec is stubbed to skip the separate post-save
    Open/Folder/Close dialog, which is not this feature's concern."""

    PACKING = [f"packing-{n}" for n in "abc"]

    def _skip_post_save_dialog(self, monkeypatch):
        monkeypatch.setattr(QMessageBox, "exec", lambda self: None)

    def test_the_prompt_appears_when_reordering_would_help(
        self, window, monkeypatch, tmp_path: Path
    ):
        self._skip_post_save_dialog(monkeypatch)
        asked = []
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: asked.append(True) or QMessageBox.No,
        )
        w = window(self.PACKING)
        w.output.setText(str(tmp_path / "out.pdf"))
        w._save()
        assert asked

    def test_no_prompt_when_reordering_would_not_help(
        self, window, monkeypatch, tmp_path: Path
    ):
        self._skip_post_save_dialog(monkeypatch)
        asked = []
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: asked.append(True) or QMessageBox.No,
        )
        w = window(STATEMENTS)
        w.output.setText(str(tmp_path / "out.pdf"))
        w._save()
        assert not asked

    def test_saying_yes_ticks_the_checkbox_and_writes_the_smaller_document(
        self, window, monkeypatch, tmp_path: Path
    ):
        self._skip_post_save_dialog(monkeypatch)
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)

        w = window(self.PACKING)
        target = tmp_path / "out.pdf"
        w.output.setText(str(target))
        w._save()

        assert w.settings._widgets["reorder"].isChecked() is True
        assert w.session.options.reorder is True

        from pypdf import PdfReader

        assert len(PdfReader(str(target)).pages) == 2   # not 3

    def test_saying_no_leaves_the_setting_untouched_and_writes_as_configured(
        self, window, monkeypatch, tmp_path: Path
    ):
        self._skip_post_save_dialog(monkeypatch)
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)

        w = window(self.PACKING)
        target = tmp_path / "out.pdf"
        w.output.setText(str(target))
        w._save()

        assert w.session.options.reorder is False

        from pypdf import PdfReader

        assert len(PdfReader(str(target)).pages) == 3

    def test_saying_no_does_not_ask_again_on_an_immediate_second_save(
        self, window, monkeypatch, tmp_path: Path
    ):
        self._skip_post_save_dialog(monkeypatch)
        asked = []
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: asked.append(True) or QMessageBox.No,
        )
        w = window(self.PACKING)
        w.output.setText(str(tmp_path / "out.pdf"))
        w._save()
        w._save()
        assert len(asked) == 1

    def test_a_settings_change_after_declining_re_arms_the_prompt(
        self, window, monkeypatch, tmp_path: Path
    ):
        self._skip_post_save_dialog(monkeypatch)
        asked = []
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: asked.append(True) or QMessageBox.No,
        )
        w = window(self.PACKING)
        w.output.setText(str(tmp_path / "out.pdf"))
        w._save()
        w.settings._widgets["separator"].setChecked(True)
        w._save()
        assert len(asked) == 2


class TestPostSaveDialog:
    """The three-choice dialog after a successful save (#6).

    `QMessageBox.exec` is stubbed to click one of the real buttons before
    returning, rather than faking the whole dialog, so `clickedButton()` sees
    exactly what a real click would set. `MainWindow._open` is stubbed
    separately so no test ever actually launches Finder or a PDF viewer.
    """

    def _click(self, monkeypatch, label: str | None):
        """Make the next QMessageBox.exec() click the button with this text
        (or nothing at all, simulating the dialog's own close button)."""

        def fake_exec(box_self):
            if label is None:
                return
            for button in box_self.buttons():
                if button.text() == label:
                    button.click()
                    return

        monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    def test_the_dialog_offers_exactly_three_choices(self, window, monkeypatch):
        """Button order is a platform styling concern, not a behaviour to pin
        down — only the set of choices matters here."""
        seen = []

        def fake_exec(box_self):
            seen.extend(b.text() for b in box_self.buttons())

        monkeypatch.setattr(QMessageBox, "exec", fake_exec)
        w = window(["statement-a"])
        w._offer_to_open(Path("/tmp/whatever.pdf"), w.session.packing())
        assert set(seen) == {"Open Document", "Open Folder", "Close"}

    def test_open_document_opens_the_file_and_the_dialog_is_gone(
        self, window, monkeypatch, tmp_path: Path
    ):
        opened = []
        monkeypatch.setattr("eco_print.gui.app.MainWindow._open", lambda self, p: opened.append(p))
        self._click(monkeypatch, "Open Document")

        w = window(STATEMENTS)
        target = tmp_path / "out.pdf"
        w.output.setText(str(target))
        w._save()

        assert opened == [target]

    def test_open_folder_opens_the_containing_directory(
        self, window, monkeypatch, tmp_path: Path
    ):
        opened = []
        monkeypatch.setattr("eco_print.gui.app.MainWindow._open", lambda self, p: opened.append(p))
        self._click(monkeypatch, "Open Folder")

        w = window(STATEMENTS)
        target = tmp_path / "sub" / "out.pdf"
        w.output.setText(str(target))
        w._save()

        assert opened == [target.parent]

    def test_close_opens_nothing(self, window, monkeypatch, tmp_path: Path):
        opened = []
        monkeypatch.setattr("eco_print.gui.app.MainWindow._open", lambda self, p: opened.append(p))
        self._click(monkeypatch, "Close")

        w = window(STATEMENTS)
        w.output.setText(str(tmp_path / "out.pdf"))
        w._save()

        assert opened == []

    def test_dismissing_the_dialog_without_a_button_opens_nothing(
        self, window, monkeypatch, tmp_path: Path
    ):
        """The dialog's own close control (or Escape) must behave like Close,
        not crash or fall through to opening something."""
        opened = []
        monkeypatch.setattr("eco_print.gui.app.MainWindow._open", lambda self, p: opened.append(p))
        self._click(monkeypatch, None)

        w = window(STATEMENTS)
        w.output.setText(str(tmp_path / "out.pdf"))
        w._save()

        assert opened == []


class TestCloseConfirmationAndExit:
    """UC-03: prompt only for real, unsaved loss; Exit goes through the same
    path as the window's own close control (#4, #5)."""

    def test_closing_an_empty_window_needs_no_confirmation(self, window):
        w = window()
        event = _FakeCloseEvent()
        w.closeEvent(event)
        assert event.accepted

    def test_closing_with_unsaved_documents_asks(self, window, monkeypatch):
        asked = []
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: asked.append(True) or QMessageBox.No,
        )
        w = window(STATEMENTS)
        event = _FakeCloseEvent()
        w.closeEvent(event)
        assert asked
        assert not event.accepted   # "No" was chosen

    def test_closing_right_after_a_save_needs_no_confirmation(
        self, window, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setattr(QMessageBox, "exec", lambda self: None)
        w = window(STATEMENTS)
        w.output.setText(str(tmp_path / "out.pdf"))
        w._save()

        event = _FakeCloseEvent()
        w.closeEvent(event)
        assert event.accepted

    def test_a_change_after_saving_re_arms_the_prompt(
        self, window, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setattr(QMessageBox, "exec", lambda self: None)
        asked = []
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: asked.append(True) or QMessageBox.No,
        )
        w = window(STATEMENTS)
        w.output.setText(str(tmp_path / "out.pdf"))
        w._save()
        w.list.setCurrentRow(0)
        w._remove_selected()

        event = _FakeCloseEvent()
        w.closeEvent(event)
        assert asked

    def test_choosing_yes_lets_the_window_close(self, window, monkeypatch):
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
        w = window(STATEMENTS)
        event = _FakeCloseEvent()
        w.closeEvent(event)
        assert event.accepted

    def test_exit_routes_through_the_same_close_path(self, window, monkeypatch):
        """An Exit button that skipped closeEvent would be a second,
        inconsistent way to quit."""
        calls = []
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **k: calls.append(True) or QMessageBox.No,
        )
        w = window(STATEMENTS)
        exit_button = _find_button(w, "Exit")
        assert exit_button is not None
        exit_button.click()
        assert calls   # the same confirmation fired


class _FakeCloseEvent:
    def __init__(self):
        self.accepted = False
        self.ignored = False

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


def _find_button(widget, text):
    from PySide6.QtWidgets import QPushButton

    for button in widget.findChildren(QPushButton):
        if button.text() == text:
            return button
    return None


class TestDetailsPane:
    """UC-03, UC-08: "show detection details" must have a visible effect —
    the gap that shipped it inert in M6."""

    def test_the_pane_starts_hidden(self, window):
        assert window(["statement-a"]).details_pane.isHidden()

    def test_ticking_the_checkbox_shows_the_pane(self, window, qt_app):
        w = window(["statement-a"])
        w.show()
        qt_app.processEvents()
        w.settings._widgets["verbose"].setChecked(True)
        qt_app.processEvents()
        assert w.details_pane.isVisible()

    def test_unticking_hides_it_again(self, window, qt_app):
        w = window(["statement-a"])
        w.show()
        qt_app.processEvents()
        w.settings._widgets["verbose"].setChecked(True)
        w.settings._widgets["verbose"].setChecked(False)
        qt_app.processEvents()
        assert not w.details_pane.isVisible()

    def test_the_pane_contains_the_real_report(self, window):
        w = window(["with-footer"])
        w.settings._widgets["verbose"].setChecked(True)
        assert "gap-cut" in w.details.toPlainText()

    def test_the_pane_follows_list_changes(self, window):
        w = window(["statement-a"])
        w.settings._widgets["verbose"].setChecked(True)
        w.list.setCurrentRow(0)
        w._remove_selected()
        assert "statement-a.pdf" not in w.details.toPlainText()
        assert "nothing to report" in w.details.toPlainText()

    def test_the_pane_gets_real_width_not_just_visibility(self, window, qt_app):
        """Regression: `setVisible(True)` alone left the splitter section at
        the 0px it was given at construction, so the pane was "visible" and
        yet showed nothing on screen."""
        w = window(["statement-a"])
        w.resize(1200, 700)
        w.show()
        qt_app.processEvents()
        w.settings._widgets["verbose"].setChecked(True)
        qt_app.processEvents()
        assert w.splitter.sizes()[-1] > 50


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

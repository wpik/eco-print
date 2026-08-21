"""The main window (UC-03, UC-04, UC-08).

Glue only: the document list lives in `state.Session`, the options panel is
generated from `Options`, and the work is `pipeline.run`. What is left here is
wiring and wording.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..compose import write
from ..settings import Options
from .cropview import CropView
from .settings_panel import SettingsPanel, load_remembered, remember
from .state import Session

WINDOW_TITLE = "eco-print"
DROP_HINT = "Drop PDFs or folders here"


class MainWindow(QMainWindow):
    def __init__(self, initial: list[str] | None = None, store=None):
        """`store` is injectable so tests never read or write real preferences."""
        super().__init__()
        self._store = store
        self.session = Session(options=load_remembered(store=store))
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1000, 720)
        self.setAcceptDrops(True)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.currentRowChanged.connect(self._show_selected)
        self.list.model().rowsMoved.connect(self._rows_moved)

        self.crop = CropView(self._crop_changed)
        self.settings = SettingsPanel(self.session.options, self._options_changed)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setFont(QFont("Menlo, Consolas, monospace"))

        self.status = QLabel("no documents yet")
        self.output = QLineEdit(str(Path.home() / "combined.pdf"))
        self.save = QPushButton("Save PDF")
        self.save.clicked.connect(self._save)
        self.save.setEnabled(False)

        self.setCentralWidget(self._build_layout())
        self._install_shortcuts()

        if initial:
            self._add([Path(p) for p in initial])

    # -- layout -------------------------------------------------------------

    def _build_layout(self) -> QWidget:
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Documents"))
        left_layout.addWidget(self.list, 1)

        hint = QLabel(DROP_HINT)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: palette(mid); padding: 6px;")
        left_layout.addWidget(hint)

        buttons = QHBoxLayout()
        for text, slot in (
            ("Add files…", self._choose_files),
            ("Remove", self._remove_selected),
            ("Clear", self._clear),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        left_layout.addLayout(buttons)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Preview"))
        right_layout.addWidget(self.crop, 1)

        crop_buttons = QHBoxLayout()
        for text, slot in (
            ("Reset to auto", self._reset_current),
            ("Reset all", self._reset_all),
            ("Apply crop to all", self._apply_to_all),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            crop_buttons.addWidget(button)
        crop_buttons.addStretch(1)
        right_layout.addLayout(crop_buttons)

        self.details_pane = QWidget()
        details_layout = QVBoxLayout(self.details_pane)
        details_layout.addWidget(QLabel("Details"))
        details_layout.addWidget(self.details, 1)
        self.details_pane.hide()
        self._details_pane_shown = False

        self.splitter = QSplitter()
        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.addWidget(self.details_pane)
        self.splitter.setSizes([340, 480, 0])

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output:"))
        output_row.addWidget(self.output, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._choose_output)
        output_row.addWidget(browse)

        bottom = QHBoxLayout()
        bottom.addWidget(self.status, 1)

        copy = QPushButton("Copy as command line")
        copy.clicked.connect(self._copy_command_line)
        copy.setAutoDefault(False)
        bottom.addWidget(copy)

        # Save PDF is the window's default button: Enter activates it (in
        # addition to the existing Cmd+S shortcut) and macOS renders it in
        # blue for as long as it holds that role. The other two buttons are
        # explicitly excluded from ever borrowing that role via focus.
        self.save.setDefault(True)
        bottom.addWidget(self.save)

        self.exit_button = QPushButton("Exit")
        self.exit_button.clicked.connect(self.close)
        self.exit_button.setAutoDefault(False)
        bottom.addWidget(self.exit_button)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self.splitter, 1)
        layout.addWidget(self.settings)
        layout.addLayout(output_row)
        layout.addLayout(bottom)
        return root

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence.Delete, self.list, self._remove_selected)
        QShortcut(QKeySequence.Save, self, self._save)

    # -- drag and drop (UC-03) ----------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        if paths:
            self._add(paths)
            event.acceptProposedAction()

    # -- the document list --------------------------------------------------

    def _add(self, paths: list[Path]) -> None:
        before = len(self.session.errors)
        added = self.session.add_paths(paths)
        self._rebuild_rows()
        if added:
            self.list.setCurrentRow(len(self.session.entries) - len(added))
        self._refresh()

        new_errors = self.session.errors[before:]
        if new_errors and not added:
            self._warn(new_errors)
        elif new_errors:
            # Valid PDFs in the same drop are still added (UC-03).
            self.status.setText(
                f"{self.status.text()}  ·  {len(new_errors)} skipped"
            )

    def _rebuild_rows(self) -> None:
        self.list.blockSignals(True)
        current = self.list.currentRow()
        self.list.clear()
        for entry in self.session.entries:
            item = QListWidgetItem(self._row_text(entry))
            if entry.is_blank:
                item.setForeground(Qt.gray)
            self.list.addItem(item)
        self.list.blockSignals(False)
        if 0 <= current < self.list.count():
            self.list.setCurrentRow(current)

    def _row_text(self, entry) -> str:
        if entry.is_blank:
            return f"{entry.label}  ·  blank, skipped"
        mark = "  ✎" if entry.is_manual else ""
        return f"{entry.label}  ·  {entry.height:.0f} pt{mark}"

    def _rows_moved(self, _parent, start, _end, _dest, row) -> None:
        """Keep the session in step when a row is dragged (UC-03)."""
        destination = row - 1 if row > start else row
        self.session.move(start, destination)
        self._refresh()

    def _remove_selected(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        self.session.remove(row)
        self._rebuild_rows()
        self._refresh()

    def _clear(self) -> None:
        self.session.clear()
        self.list.clear()
        self.crop.clear()
        self._refresh()

    # -- crops (UC-04) ------------------------------------------------------

    def _show_selected(self, row: int) -> None:
        if not (0 <= row < len(self.session.entries)):
            self.crop.clear()
            return
        entry = self.session.entries[row]
        box = entry.box
        if box is None:
            self.crop.clear()
            return
        self.crop.show_page(entry.page, box.top, box.bottom)

    def _crop_changed(self, top: float, bottom: float) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        self.session.set_manual_box(row, top, bottom)
        self._rebuild_rows()
        self._refresh()

    def _reset_current(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        self.session.reset_to_auto(row)
        self._rebuild_rows()
        self._show_selected(row)
        self._refresh()

    def _reset_all(self) -> None:
        self.session.reset_all_to_auto()
        self._rebuild_rows()
        self._show_selected(self.list.currentRow())
        self._refresh()

    def _apply_to_all(self) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        changed = self.session.apply_box_to_all(row)
        self._rebuild_rows()
        self._refresh()
        self.status.setText(f"{self.status.text()}  ·  applied to {changed} pages")

    # -- settings (UC-08) ---------------------------------------------------

    def _options_changed(self, options: Options) -> None:
        self.session.apply_options(options)
        remember(options, store=self._store)
        self._rebuild_rows()
        self._show_selected(self.list.currentRow())
        self._refresh()

    # -- output -------------------------------------------------------------

    def _choose_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(self, "Add PDFs", "", "PDF files (*.pdf)")
        if names:
            self._add([Path(name) for name in names])

    def _choose_output(self) -> None:
        name, _ = QFileDialog.getSaveFileName(
            self, "Save as", self.output.text(), "PDF files (*.pdf)"
        )
        if name:
            self.output.setText(name)

    def _copy_command_line(self) -> None:
        line = self.session.command_line(Path(self.output.text()))
        QGuiApplication.clipboard().setText(line)
        self.status.setText("command line copied to the clipboard")

    def _save(self) -> None:
        packing = self.session.packing()
        if packing is None:
            return
        target = Path(self.output.text()).expanduser()
        try:
            write(packing, target, self.session.options)
        except OSError as exc:
            QMessageBox.warning(self, WINDOW_TITLE, f"Could not write {target}:\n{exc}")
            return
        self.session.mark_saved()
        self._offer_to_open(target, packing)

    def _offer_to_open(self, target: Path, packing) -> None:
        """After a successful save: open the document, open its folder, or
        just close the dialog. Opening either way also closes it (#6)."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle(WINDOW_TITLE)
        dialog.setText(
            f"Wrote {target}\n{packing.sheet_count} pages "
            f"from {packing.block_count} blocks."
        )
        open_document = dialog.addButton("Open Document", QMessageBox.AcceptRole)
        open_folder = dialog.addButton("Open Folder", QMessageBox.ActionRole)
        close = dialog.addButton("Close", QMessageBox.RejectRole)
        dialog.setDefaultButton(close)
        dialog.exec()

        clicked = dialog.clickedButton()
        if clicked is open_document:
            self._open(target)
        elif clicked is open_folder:
            self._open(target.parent)

    def _open(self, path: Path) -> None:
        """Hand `path` to the OS. Its own method so tests can stub it out
        instead of actually launching Finder or a PDF viewer."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # -- status -------------------------------------------------------------

    def _refresh(self) -> None:
        estimate = self.session.estimate()
        self.status.setText(estimate.describe())
        self.save.setEnabled(estimate.blocks > 0)
        self._refresh_details()

    def _refresh_details(self) -> None:
        """Show or hide the Details pane, and keep its text current (UC-08).

        Visibility follows `Options.verbose` directly, so the checkbox has a
        visible effect the moment it is ticked — the gap that made it inert
        in the first place. A splitter section that is merely `setVisible`
        keeps whatever width it last had, which is 0 the first time this pane
        appears, so an explicit size is given when it goes from hidden to
        shown.
        """
        visible = self.session.options.verbose
        was_visible = self._details_pane_shown
        self.details_pane.setVisible(visible)
        self._details_pane_shown = visible
        if visible:
            self.details.setPlainText(self.session.details())
            if not was_visible:
                sizes = self.splitter.sizes()
                sizes[-1] = max(sizes[-1], 280)
                self.splitter.setSizes(sizes)

    def _warn(self, errors) -> None:
        detail = "\n".join(f"{e.path.name}: {e.reason}" for e in errors[:8])
        QMessageBox.warning(self, WINDOW_TITLE, f"Could not use:\n{detail}")

    def closeEvent(self, event) -> None:  # noqa: N802
        """Ask before closing only when something would actually be lost.

        An empty window, or one whose current state was just written to disk,
        closes immediately. Any further change re-arms the prompt (UC-03).
        """
        if not self.session.dirty:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            WINDOW_TITLE,
            "Close without saving the current documents?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        event.accept() if answer == QMessageBox.Yes else event.ignore()


def run_app(paths: list[str]) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(paths)
    window.show()
    return app.exec()

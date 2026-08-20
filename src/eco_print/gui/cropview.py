"""The interactive crop editor (UC-04).

The escape hatch that lets detection be aggressive: whatever the largest-gap
rule decides, the user can drag the top and bottom edges to whatever they meant.
Edges snap to nearby ink boundaries, so cutting cleanly between two paragraphs
needs no precision.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from ..detect import BAND_MERGE_PT, bands, ink_rows, render_gray
from ..model import SourcePage

#: How close a dragged edge must come to an ink boundary to snap to it, in points.
SNAP_PT = 6.0

#: Grab radius for an edge, in screen pixels.
GRAB_PX = 6


class CropView(QWidget):
    """A rendered page with a draggable crop region.

    Coordinates: the widget works in PDF points measured from the page top,
    which is how a reader thinks about a page, and converts to PDF's
    bottom-up y only at the boundary with the rest of the program.
    """

    def __init__(self, on_crop: Callable[[float, float], None]):
        super().__init__()
        self._on_crop = on_crop
        self._page: SourcePage | None = None
        self._pixmap: QPixmap | None = None
        self._boundaries: list[float] = []
        self._top = 0.0            # points from the page top
        self._bottom = 0.0
        self._dragging: str | None = None
        self.setMinimumSize(240, 320)
        self.setMouseTracking(True)

    # -- content ------------------------------------------------------------

    def show_page(self, page: SourcePage, top: float, bottom: float) -> None:
        """Display `page` with a crop region given in PDF points (bottom-up)."""
        if self._page is None or page != self._page:
            self._page = page
            self._pixmap = _pixmap_for(page)
            self._boundaries = _ink_boundaries(page)
        self._top = page.height - top
        self._bottom = page.height - bottom
        self.update()

    def clear(self) -> None:
        self._page = None
        self._pixmap = None
        self.update()

    # -- painting -----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(240, 240, 240))
        if self._pixmap is None or self._page is None:
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(self.rect(), Qt.AlignCenter, "select a document")
            return

        target = self._page_rect()
        painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
        painter.setPen(QColor(180, 180, 180))
        painter.drawRect(target)

        scale = target.height() / self._page.height
        top_y = target.top() + self._top * scale
        bottom_y = target.top() + self._bottom * scale

        # Everything outside the crop is dimmed, so what will print is obvious.
        shade = QColor(255, 255, 255, 170)
        painter.fillRect(
            QRectF(target.left(), target.top(), target.width(), top_y - target.top()),
            shade,
        )
        painter.fillRect(
            QRectF(target.left(), bottom_y, target.width(), target.bottom() - bottom_y),
            shade,
        )

        painter.setPen(QColor(30, 110, 200))
        painter.drawLine(int(target.left()), int(top_y), int(target.right()), int(top_y))
        painter.drawLine(
            int(target.left()), int(bottom_y), int(target.right()), int(bottom_y)
        )

        height_pt = self._bottom - self._top
        painter.setPen(QColor(30, 110, 200))
        painter.drawText(
            QPoint(int(target.left()) + 4, int(bottom_y) + 14),
            f"{height_pt:.0f} pt / {height_pt * 25.4 / 72:.0f} mm",
        )

    def _page_rect(self) -> QRectF:
        """Where the page image sits inside the widget, preserving its aspect."""
        assert self._page is not None
        margin = 8
        available_w = self.width() - 2 * margin
        available_h = self.height() - 2 * margin
        scale = min(available_w / self._page.width, available_h / self._page.height)
        width = self._page.width * scale
        height = self._page.height * scale
        return QRectF(
            margin + (available_w - width) / 2,
            margin + (available_h - height) / 2,
            width,
            height,
        )

    # -- dragging -----------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._page is None:
            return
        target = self._page_rect()
        scale = target.height() / self._page.height
        y = event.position().y()
        top_y = target.top() + self._top * scale
        bottom_y = target.top() + self._bottom * scale

        if abs(y - top_y) <= GRAB_PX:
            self._dragging = "top"
        elif abs(y - bottom_y) <= GRAB_PX:
            self._dragging = "bottom"

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._page is None:
            return
        target = self._page_rect()
        scale = target.height() / self._page.height
        y = event.position().y()

        if self._dragging is None:
            top_y = target.top() + self._top * scale
            bottom_y = target.top() + self._bottom * scale
            near = min(abs(y - top_y), abs(y - bottom_y)) <= GRAB_PX
            self.setCursor(Qt.SizeVerCursor if near else Qt.ArrowCursor)
            return

        position = (y - target.top()) / scale
        if not (event.modifiers() & Qt.AltModifier):
            position = self._snap(position)

        if self._dragging == "top":
            self._top = max(0.0, min(position, self._bottom - 1))
        else:
            self._bottom = min(self._page.height, max(position, self._top + 1))
        self.update()
        self._emit()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._dragging = None

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Arrows nudge the bottom edge; Shift makes the step coarse (UC-04)."""
        if self._page is None:
            return
        step = 10.0 if event.modifiers() & Qt.ShiftModifier else 1.0
        if event.key() == Qt.Key_Down:
            self._bottom = min(self._page.height, self._bottom + step)
        elif event.key() == Qt.Key_Up:
            self._bottom = max(self._top + 1, self._bottom - step)
        else:
            return
        self.update()
        self._emit()

    def _snap(self, position: float) -> float:
        """Pull a dragged edge onto a nearby band boundary."""
        if not self._boundaries:
            return position
        nearest = min(self._boundaries, key=lambda b: abs(b - position))
        return nearest if abs(nearest - position) <= SNAP_PT else position

    def _emit(self) -> None:
        """Report the crop in PDF points (bottom-up), as the rest expects."""
        assert self._page is not None
        self._on_crop(self._page.height - self._top, self._page.height - self._bottom)


def _pixmap_for(page: SourcePage) -> QPixmap:
    gray = render_gray(page)
    height, width = gray.shape
    contiguous = gray.copy()
    image = QImage(
        contiguous.data, width, height, width, QImage.Format_Grayscale8
    ).copy()
    return QPixmap.fromImage(image)


def _ink_boundaries(page: SourcePage) -> list[float]:
    """Band edges, in points from the page top, for snapping."""
    gray = render_gray(page)
    scale = page.height / gray.shape[0]
    rows = ink_rows(gray)
    edges: list[float] = []
    for first, last in bands(rows, BAND_MERGE_PT / scale):
        edges.append(first * scale)
        edges.append((last + 1) * scale)
    return edges

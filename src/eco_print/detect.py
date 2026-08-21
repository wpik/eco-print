"""Deciding which part of a page is worth printing (UC-05).

A PDF does not record where its content is; it records drawing operations. So
detection works on a **rendered raster** rather than the object model, which is
immune to the tricks that defeat object inspection: white rectangles painted over
content, off-page objects, clipped XObjects, vector art and scans.

The rule, in one line: cut at the largest whitespace gap, but only when that gap
is structural *and* what falls below it is a small minority of the page's ink.
The second condition is the safety valve — without it, a document whose real
content resumes after a wide gap would be amputated.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium

from .model import ContentBox, SourceError, SourcePage
from .settings import Options

log = logging.getLogger(__name__)

#: Rendering resolution. At 72 dpi one pixel is one PDF point, which keeps the
#: arithmetic honest and is ample for finding where ink is.
RENDER_DPI = 72.0

#: Anything lighter than this counts as paper, not ink. Loose enough to ignore
#: faint background tints and JPEG ringing around text.
WHITE_THRESHOLD = 250

#: Ink within this distance of a page edge is treated as a scan border or a
#: bleed rule rather than content.
EDGE_ZONE_PX = 6

#: A row this close to spanning the full width, inside the edge zone, is a
#: border rather than a line of text.
EDGE_SPAN_RATIO = 0.98

#: Ink rows closer together than this belong to the same band. Ordinary line
#: spacing, not a structural break.
BAND_MERGE_PT = 12.0

#: A gap must be at least this fraction of the page height to be structural.
STRUCTURAL_GAP_RATIO = 0.15

#: ...and what it cuts away must be no more than this share of the page's ink.
#: A footnote's worth, not a section's worth.
MAX_DISCARD_RATIO = 0.25


@dataclass(frozen=True)
class Detection:
    """What detection decided about one page, and why.

    `method` is reported by `--verbose` so a surprising crop can be explained
    without guesswork:

    * ``gap-cut``   — the largest-gap rule fired; `dropped` points were discarded
    * ``ink-box``   — the rule was rejected or absent; the whole ink area is kept
    * ``full-ink``  — the user asked for the whole ink area with ``--full-ink``
    * ``blank``     — no ink at all; the page yields no block
    """

    page: SourcePage
    box: ContentBox | None
    method: str
    dropped: float = 0.0

    @property
    def is_blank(self) -> bool:
        return self.box is None

    def describe(self) -> str:
        """One line for the verbose report."""
        if self.box is None:
            return f"{self.page.label}: blank, skipped"
        detail = f"{self.box.height:.0f}pt kept"
        if self.dropped:
            detail += f", {self.dropped:.0f}pt dropped"
        return f"{self.page.label}: {detail} ({self.method})"


@dataclass
class DetectResult:
    """The outcome of detecting a batch, mirroring `LoadResult`."""

    detections: list[Detection]
    errors: list[SourceError]

    @property
    def boxed(self) -> list[Detection]:
        """Only the pages that yielded something printable."""
        return [d for d in self.detections if d.box is not None]

    @property
    def blank(self) -> list[Detection]:
        return [d for d in self.detections if d.box is None]

    @property
    def ok(self) -> bool:
        return not self.errors


class DetectionFailed(Exception):
    """A page could not be rendered. Carries the sentence shown to the user."""


# -- rendering -------------------------------------------------------------

_raster_cache: dict[tuple, np.ndarray] = {}
_CACHE_LIMIT = 32


def render_gray(page: SourcePage) -> np.ndarray:
    """Render one page to a greyscale array, one pixel per point.

    Cached: the GUI re-detects on every change to `--pad` or `--full-ink`, and
    rendering is the only expensive step in this module.
    """
    try:
        stat = page.path.stat()
    except OSError as exc:
        raise DetectionFailed(f"cannot be read ({exc.strerror or exc})") from exc

    key = (str(page.path), stat.st_mtime_ns, stat.st_size, page.page_index)
    cached = _raster_cache.get(key)
    if cached is not None:
        return cached

    array = _render(page)
    if len(_raster_cache) >= _CACHE_LIMIT:
        _raster_cache.pop(next(iter(_raster_cache)))
    _raster_cache[key] = array
    return array


def _render(page: SourcePage) -> np.ndarray:
    try:
        document = pdfium.PdfDocument(str(page.path), password=page.password)
        try:
            bitmap = document[page.page_index].render(
                scale=RENDER_DPI / 72.0, grayscale=True
            )
            return np.asarray(bitmap.to_pil().convert("L"))
        finally:
            document.close()
    except DetectionFailed:
        raise
    except Exception as exc:
        raise DetectionFailed(
            f"page {page.page_index + 1} could not be rendered "
            f"({type(exc).__name__})"
        ) from exc


def clear_cache() -> None:
    """Forget every rendered page. For tests, and for the GUI on reset."""
    _raster_cache.clear()


# -- analysis --------------------------------------------------------------


def ink_rows(gray: np.ndarray) -> np.ndarray:
    """Which rows of the raster contain ink, ignoring page-edge artefacts.

    A scan border or a bleed rule hugging the sheet edge would otherwise anchor
    the content box to the paper's edge and defeat the whole exercise.
    """
    ink = gray < WHITE_THRESHOLD
    height, width = ink.shape

    # A border down the side would make every row inky, so the outermost
    # columns do not get a vote.
    inner = ink[:, EDGE_ZONE_PX : max(width - EDGE_ZONE_PX, EDGE_ZONE_PX + 1)]
    rows = inner.any(axis=1)

    # Near-full-width rules within the edge zone are borders, not content.
    span = ink.sum(axis=1)
    edge = np.zeros(height, dtype=bool)
    edge[:EDGE_ZONE_PX] = True
    edge[height - EDGE_ZONE_PX :] = True
    rows &= ~(edge & (span >= width * EDGE_SPAN_RATIO))
    return rows


def bands(rows: np.ndarray, merge_px: float) -> list[tuple[int, int]]:
    """Group ink rows into bands, merging any closer together than `merge_px`.

    Returns inclusive (first_row, last_row) pairs, top-down.
    """
    indices = np.flatnonzero(rows)
    if indices.size == 0:
        return []

    grouped: list[tuple[int, int]] = []
    start = previous = int(indices[0])
    for row in indices[1:]:
        row = int(row)
        if row - previous > merge_px:
            grouped.append((start, previous))
            start = row
        previous = row
    grouped.append((start, previous))
    return grouped


def choose_bands(
    grouped: list[tuple[int, int]], rows: np.ndarray, page_height_px: int
) -> tuple[list[tuple[int, int]], str, int]:
    """Apply the largest-gap rule (UC-05).

    Returns the bands to keep, the method name, and how many pixels of page
    height were discarded.
    """
    if len(grouped) < 2:
        return grouped, "ink-box", 0

    gaps = [
        (grouped[i + 1][0] - grouped[i][1] - 1, i) for i in range(len(grouped) - 1)
    ]
    widest, index = max(gaps)

    if widest < page_height_px * STRUCTURAL_GAP_RATIO:
        # Line spacing, not a structural break.
        return grouped, "ink-box", 0

    kept, discarded = grouped[: index + 1], grouped[index + 1 :]
    kept_ink = sum(int(rows[a : b + 1].sum()) for a, b in kept)
    discarded_ink = sum(int(rows[a : b + 1].sum()) for a, b in discarded)
    total_ink = kept_ink + discarded_ink

    if total_ink and discarded_ink / total_ink > MAX_DISCARD_RATIO:
        # What lies below is a section, not a footnote. Keep everything.
        return grouped, "ink-box", 0

    return kept, "gap-cut", discarded[-1][1] - kept[-1][1]


# -- the public step -------------------------------------------------------


def detect(page: SourcePage, options: Options | None = None) -> Detection:
    """Find the content box of one page."""
    options = options or Options()
    gray = render_gray(page)
    raster_height = gray.shape[0]
    if raster_height == 0:
        return Detection(page, None, "blank")

    # The raster is a whole number of pixels; the page rarely is.
    scale = page.height / raster_height

    rows = ink_rows(gray)
    grouped = bands(rows, BAND_MERGE_PT / scale)
    if not grouped:
        log.debug("%s: no ink", page.label)
        return Detection(page, None, "blank")

    if options.full_ink:
        kept, method, dropped_px = grouped, "full-ink", 0
    else:
        kept, method, dropped_px = choose_bands(grouped, rows, raster_height)

    first_row, last_row = kept[0][0], kept[-1][1]
    box = _box_from_rows(page, first_row, last_row, scale, options, method)
    detection = Detection(page, box, method, dropped_px * scale)
    log.debug("%s", detection.describe())
    return detection


def _box_from_rows(
    page: SourcePage,
    first_row: int,
    last_row: int,
    scale: float,
    options: Options,
    method: str,
) -> ContentBox:
    """Turn a row range into a padded content box in PDF coordinates.

    Raster rows count downwards from the page top; PDF y counts upwards from the
    bottom, so the two are mirror images of one another.
    """
    top = page.height - first_row * scale + options.pad
    bottom = page.height - (last_row + 1) * scale - options.pad
    return ContentBox(
        left=0.0,
        bottom=max(bottom, 0.0),
        right=page.width,
        top=min(top, page.height),
        origin="full-ink" if method == "full-ink" else "auto",
    )


def detect_all(
    pages: list[SourcePage], options: Options | None = None
) -> DetectResult:
    """Detect a batch, isolating failures the way the loader does (UC-07)."""
    detections: list[Detection] = []
    errors: list[SourceError] = []

    for page in pages:
        try:
            detections.append(detect(page, options))
        except DetectionFailed as exc:
            log.warning("skipping %s: %s", page.label, exc)
            errors.append(SourceError(Path(page.path), str(exc)))

    return DetectResult(detections=detections, errors=errors)

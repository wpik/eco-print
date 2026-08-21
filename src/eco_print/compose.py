"""Writing the packed sheets out as a PDF (UC-06, UC-07).

Blocks are placed by cropping the source page to its content box and merging it
onto a blank sheet at the offset the layout asked for. Nothing is scaled: a
distance measured on the output equals the same distance measured on the source.
"""
from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import ContentStream, RectangleObject

from .model import Block, ContentBox
from .packer import PackResult, Placement, layout
from .settings import Options

log = logging.getLogger(__name__)

#: Thickness of the optional cut line, in points.
SEPARATOR_THICKNESS = 0.5

#: Dash pattern for the cut line: 4pt on, 3pt off, in PDF content-stream units.
SEPARATOR_DASH = "[4 3] 0 d"


def write(result: PackResult, output: Path, options: Options | None = None) -> Path:
    """Compose the packed sheets and write them to `output`."""
    options = options or Options()
    width, height = options.page_dimensions()

    writer = PdfWriter()
    readers: dict[Path, PdfReader] = {}

    for sheet in result.sheets:
        target = writer.add_blank_page(width, height)
        placements = layout(sheet, options)
        for placement in placements:
            _place(target, placement, options, readers)
        if options.separator and len(placements) > 1:
            _draw_separators(target, placements, options)

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "wb") as handle:
        writer.write(handle)
    log.debug("wrote %s (%d sheets)", output, len(result.sheets))
    return output


def _reader_for(path: Path, password: str | None, cache: dict[Path, PdfReader]) -> PdfReader:
    """One reader per document, reused across its pages."""
    reader = cache.get(path)
    if reader is None:
        reader = PdfReader(str(path))
        if reader.is_encrypted and password is not None:
            reader.decrypt(password)
        cache[path] = reader
    return reader


def _place(
    target, placement: Placement, options: Options, readers: dict[Path, PdfReader]
) -> None:
    """Crop one source page to its box and merge it onto the sheet."""
    block = placement.block
    page = _cropped_page(block, readers)

    sheet_width = options.page_dimensions()[0]
    dx = _horizontal_offset(block, sheet_width, options)
    dy = (placement.top - block.height) - block.box.bottom

    target.merge_transformed_page(page, Transformation().translate(dx, dy))


def _cropped_page(block: Block, readers: dict[Path, PdfReader]):
    """The source page, with every box narrowed to the content region.

    The four boxes are set together because viewers disagree about which one
    governs; annotations are dropped because their coordinates stop meaning
    anything once the page is cropped and moved, and a malformed one — missing
    the `/Rect` the specification requires — would otherwise fail the merge
    (UC-07).
    """
    source = block.page
    reader = _reader_for(source.path, source.password, readers)
    page = reader.pages[source.page_index]
    page.pop("/Annots", None)

    box = block.box
    rect = RectangleObject((box.left, box.bottom, box.right, box.top))
    for name in ("mediabox", "cropbox", "trimbox", "bleedbox"):
        setattr(page, name, RectangleObject(rect))
    return page


def _horizontal_offset(block: Block, sheet_width: float, options: Options) -> float:
    """Centre a block that fits; left-align one that does not (UC-07)."""
    if block.width <= sheet_width:
        return (sheet_width - block.width) / 2 - block.box.left
    return options.margin - block.box.left


def _draw_separators(target, placements: list[Placement], options: Options) -> None:
    """Draw a dashed cut line centred in each gap between blocks.

    The line runs from the left margin to the right margin, the same span a
    person would use scissors across — it is meant as a literal cutting guide,
    not a decorative divider, so it is not inset from the printable area.
    """
    width = options.page_dimensions()[0]
    left = options.margin
    right = width - options.margin
    lines = []

    for above, below in zip(placements, placements[1:]):
        bottom_of_above = above.top - above.block.height
        middle = (bottom_of_above + below.top) / 2
        lines.append(f"{left:.2f} {middle:.2f} m {right:.2f} {middle:.2f} l S")

    if not lines:
        return
    drawing = (
        "q 0.6 0.6 0.6 RG "
        f"{SEPARATOR_THICKNESS:.2f} w {SEPARATOR_DASH}\n"
        + "\n".join(lines)
        + "\nQ\n"
    )
    _append_content(target, drawing)


def _append_content(page, drawing: str) -> None:
    """Append raw drawing operators to a page's content stream."""
    existing = page.get_contents()
    data = existing.get_data() if existing is not None else b""
    stream = ContentStream(None, None)
    stream.set_data(data + b"\n" + drawing.encode("latin-1"))
    page.replace_contents(stream)


def content_boxes_of(path: Path) -> list[ContentBox]:
    """The crop box of every page of a written document. For tests."""
    reader = PdfReader(str(path))
    return [
        ContentBox(
            float(p.cropbox.left), float(p.cropbox.bottom),
            float(p.cropbox.right), float(p.cropbox.top),
        )
        for p in reader.pages
    ]

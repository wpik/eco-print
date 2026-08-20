"""Placing blocks onto as few sheets as possible (UC-06).

Blocks span the full sheet width, so only heights matter: this is a
one-dimensional problem. Two modes:

* **ordered** (default) — input order is part of the output's meaning, so the
  packer chooses page breaks only. With the sequence fixed a single greedy pass
  is optimal; no earlier break could help.
* **reordered** (``--reorder``) — the user says order does not matter, and the
  goal becomes the fewest sheets that exist for the set. That is bin packing,
  and is handled in `pack_reordered`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .model import Block
from .settings import Options


@dataclass
class Sheet:
    """One output page and the blocks placed on it, top-down."""

    blocks: list[Block] = field(default_factory=list)

    @property
    def content_height(self) -> float:
        """Height of the blocks alone, before any spacing."""
        return sum(block.height for block in self.blocks)

    def height_with_gaps(self, gap: float) -> float:
        """Height the blocks need including the minimum gaps between them."""
        if not self.blocks:
            return 0.0
        return self.content_height + gap * (len(self.blocks) - 1)

    def fits(self, block: Block, usable: float, gap: float) -> bool:
        """Whether `block` still fits, counting the gap it would need."""
        if not self.blocks:
            return True
        return self.height_with_gaps(gap) + gap + block.height <= usable


@dataclass
class Placement:
    """A block and where its top edge sits on the sheet, in PDF points."""

    block: Block
    top: float


@dataclass
class PackResult:
    """The packing, and what it cost.

    `alternative_sheets` is what the *other* mode would have produced, so the
    run can report what reordering saved — or that it would have saved nothing.
    """

    sheets: list[Sheet]
    oversized: list[Block]
    reordered: bool
    alternative_sheets: int | None = None

    @property
    def sheet_count(self) -> int:
        return len(self.sheets)

    @property
    def block_count(self) -> int:
        return sum(len(sheet.blocks) for sheet in self.sheets)

    @property
    def sheets_saved(self) -> int:
        """Sheets saved against printing every block on its own page."""
        return max(self.block_count - self.sheet_count, 0)

    @property
    def reorder_saved(self) -> int:
        """Sheets the reordering actually bought, if it was used."""
        if not self.reordered or self.alternative_sheets is None:
            return 0
        return max(self.alternative_sheets - self.sheet_count, 0)


def pack(blocks: list[Block], options: Options | None = None) -> PackResult:
    """Pack blocks according to `options`, in whichever mode is selected."""
    options = options or Options()
    if options.reorder:
        from .repack import pack_reordered

        return pack_reordered(blocks, options)
    return pack_ordered(blocks, options)


def pack_ordered(blocks: list[Block], options: Options | None = None) -> PackResult:
    """Greedy single pass, preserving input order (UC-06).

    Optimal for a fixed sequence: a block only ever starts a new sheet when it
    cannot fit the current one, and moving a break earlier can never help.
    """
    options = options or Options()
    usable = options.usable_height()
    gap = options.gap

    sheets: list[Sheet] = []
    oversized: list[Block] = []
    current = Sheet()

    for block in blocks:
        if block.height > usable:
            # Cannot fit any sheet. It gets one to itself and is reported.
            if current.blocks:
                sheets.append(current)
                current = Sheet()
            sheets.append(Sheet([block]))
            oversized.append(block)
            continue

        if not current.fits(block, usable, gap):
            sheets.append(current)
            current = Sheet()
        current.blocks.append(block)

    if current.blocks:
        sheets.append(current)

    return PackResult(sheets=sheets, oversized=oversized, reordered=False)


def lower_bound(blocks: list[Block], options: Options) -> int:
    """Fewest sheets any arrangement could possibly use.

    Each block needs its own height; every block after the first on a sheet also
    needs a gap. Ignoring which sheet they land on gives a bound that no packing
    can beat, and a packing that reaches it is provably optimal.
    """
    usable = options.usable_height()
    normal = [b for b in blocks if b.height <= usable]
    forced = len(blocks) - len(normal)
    if not normal:
        return forced
    total = sum(b.height for b in normal) + options.gap * (len(normal) - 1)
    return forced + max(1, math.ceil(total / usable))


def layout(sheet: Sheet, options: Options) -> list[Placement]:
    """Where each block sits on its sheet, top edge downwards (UC-06).

    Leftover space is spread evenly between the top margin, each gap and the
    bottom margin, so a half-full final sheet reads as deliberate layout rather
    than a truncation. `--gap` is a minimum; even distribution only adds to it.
    """
    page_height = options.page_dimensions()[1]
    count = len(sheet.blocks)
    if count == 0:
        return []

    usable = options.usable_height()
    leftover = usable - sheet.content_height
    if leftover < 0:
        # An oversized block: seat it against the top margin and let it clip.
        return [Placement(sheet.blocks[0], page_height - options.margin)]

    space = leftover / (count + 1)
    if space < options.gap:
        # Not enough slack to spread; fall back to the minimum gap, top-aligned.
        space = options.gap
        cursor = page_height - options.margin
        placements = []
        for index, block in enumerate(sheet.blocks):
            if index:
                cursor -= space
            placements.append(Placement(block, cursor))
            cursor -= block.height
        return placements

    placements = []
    cursor = page_height - options.margin - space
    for block in sheet.blocks:
        placements.append(Placement(block, cursor))
        cursor -= block.height + space
    return placements

"""Packing when input order may be given up (UC-06, ``--reorder``).

Ordered packing is greedy and provably optimal for a fixed sequence. Once the
user says order does not matter, the goal becomes the fewest sheets that exist
for the set — which is bin packing, NP-hard in general. Three tiers, cheapest
first:

1. a **lower bound**; any packing that reaches it is optimal and we stop;
2. **First-Fit-Decreasing**, guaranteed within ``11/9 · OPT + 6/9`` sheets;
3. an **exact branch-and-bound** search, for small inputs, under a time budget.

The FFD result is always in hand before the search starts, so an expired budget
costs nothing but the time spent.
"""
from __future__ import annotations

import logging
import time

from .model import Block
from .packer import PackResult, Sheet, lower_bound, pack_ordered
from .settings import Options

log = logging.getLogger(__name__)

#: Above this many blocks the exact search is not attempted: the batch is large
#: enough that FFD's guarantee is the sensible answer.
EXACT_SEARCH_LIMIT = 24

#: Seconds the exact search may spend before settling for the FFD result.
EXACT_SEARCH_BUDGET = 2.0


def pack_reordered(blocks: list[Block], options: Options | None = None) -> PackResult:
    """Pack `blocks` in any order, using as few sheets as possible."""
    options = options or Options()
    usable = options.usable_height()

    oversized = [b for b in blocks if b.height > usable]
    normal = [b for b in blocks if b.height <= usable]

    # What the default mode would have done, so the run can report the saving.
    ordered_count = pack_ordered(blocks, options).sheet_count

    sheets = _first_fit_decreasing(normal, options)
    target = lower_bound(normal, options) if normal else 0

    if normal and len(sheets) > target and len(normal) <= EXACT_SEARCH_LIMIT:
        exact = _search(normal, options, target, len(sheets))
        if exact is not None and len(exact) < len(sheets):
            log.debug("exact search improved on FFD: %d -> %d", len(sheets), len(exact))
            sheets = exact

    # Tallest first within a sheet keeps the ragged whitespace at the bottom.
    for sheet in sheets:
        sheet.blocks.sort(key=lambda b: b.height, reverse=True)

    sheets.extend(Sheet([block]) for block in oversized)

    return PackResult(
        sheets=sheets,
        oversized=oversized,
        reordered=True,
        alternative_sheets=ordered_count,
    )


def _first_fit_decreasing(blocks: list[Block], options: Options) -> list[Sheet]:
    """Tallest block first, into the first sheet with room for it."""
    usable = options.usable_height()
    sheets: list[Sheet] = []

    for block in sorted(blocks, key=lambda b: b.height, reverse=True):
        for sheet in sheets:
            if sheet.fits(block, usable, options.gap):
                sheet.blocks.append(block)
                break
        else:
            sheets.append(Sheet([block]))
    return sheets


def _search(
    blocks: list[Block], options: Options, target: int, best_known: int
) -> list[Sheet] | None:
    """Branch and bound for a packing using fewer than `best_known` sheets.

    Blocks are tried tallest first, and each is offered to every open sheet plus
    one fresh sheet. Two prunes keep the tree small: never open more sheets than
    the best answer so far, and stop the moment the lower bound is reached.
    """
    usable = options.usable_height()
    gap = options.gap
    ordered = sorted(blocks, key=lambda b: b.height, reverse=True)
    deadline = time.monotonic() + EXACT_SEARCH_BUDGET

    best: list[list[Block]] | None = None
    limit = best_known

    def recurse(index: int, sheets: list[list[Block]]) -> bool:
        """Place blocks from `index`. True means "stop, we reached the bound"."""
        nonlocal best, limit

        if time.monotonic() > deadline:
            return True
        if index == len(ordered):
            if len(sheets) < limit:
                best = [list(sheet) for sheet in sheets]
                limit = len(sheets)
            return limit <= target

        block = ordered[index]
        for sheet in sheets:
            used = sum(b.height for b in sheet) + gap * len(sheet)
            if used + block.height <= usable:
                sheet.append(block)
                if recurse(index + 1, sheets):
                    return True
                sheet.pop()

        # A fresh sheet is only worth trying if it could still beat the best.
        if len(sheets) + 1 < limit:
            sheets.append([block])
            if recurse(index + 1, sheets):
                return True
            sheets.pop()
        return False

    recurse(0, [])
    if best is None:
        return None
    return [Sheet(list(blocks_on_sheet)) for blocks_on_sheet in best]

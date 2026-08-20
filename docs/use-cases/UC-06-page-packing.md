# UC-06 — Packing blocks onto the fewest sheets

**Actor:** the tool itself.
**Goal:** place every block on as few sheets as possible while keeping the output
readable, and let the user choose whether that goal outranks input order.

## Constraints common to both modes

- Blocks are **never scaled or rotated**. A point on a block is a point on the
  output.
- Blocks are **stacked vertically**, full sheet width.
- A block plus its gap must fit within `usable = sheet height - 2 * margin`.

Because blocks span the full width, this is a **one-dimensional** problem: only
heights matter. That is what makes an exact answer affordable in the reordering
mode below.

## Mode 1 — ordered (default)

Input order is part of the output's meaning, so it is preserved: the packer
chooses page breaks, not order. With the sequence fixed, optimal packing is not a
search but a single greedy pass, and the greedy result is **provably minimal for
that fixed sequence** — no page break could be made earlier to any advantage:

    remaining = usable
    for each block:
        need = block height + (gap if the sheet is not empty else 0)
        if need > remaining and the sheet is not empty:
            start a new sheet; remaining = usable
        place the block; remaining -= need

## Mode 2 — reordered (`--reorder`)

The user declares that order does not matter. Blocks may then be rearranged
freely, and the goal becomes the true minimum sheet count over all orderings.

This is **bin packing**, which is NP-hard in general, so the tool uses a two-tier
strategy:

1. **Lower bound.** Compute `ceil(total height including gaps / usable)`. If a
   packing achieves it, that packing is optimal and the search stops immediately.
   For typical batches of similar documents this triggers at once.
2. **First-Fit-Decreasing.** Sort blocks tallest first and put each into the
   first sheet with room. FFD is the standard heuristic and is guaranteed to use
   no more than `11/9 · OPT + 6/9` sheets — at most one or two sheets off, ever.
3. **Exact search** for small inputs. When the block count is modest (a few
   dozen — the realistic case for a paper-saving tool) and FFD did not reach the
   lower bound, a branch-and-bound pass over sheet assignments finds the true
   optimum, bounded by a time budget. If the budget expires, the FFD result
   stands and nothing is lost.

Within each sheet, blocks are then emitted **tallest first**, which keeps the
ragged whitespace at the bottom of the sheet rather than between blocks.

### What the user gets told

The reordered result is only better sometimes, and the tool says which:

    3 blocks -> 2 pages  (ordered packing would use 3; --reorder saved 1)

When reordering saves nothing, the run reports that too, so the user learns that
the flag is not needed for this kind of batch.

## Distributing the leftover space

In both modes, the space left over after placing a sheet's blocks is distributed
**evenly between the top margin, each gap, and the bottom margin**. Blocks on a
half-full final sheet therefore sit spread out rather than crowded at the top,
which reads as deliberate layout instead of a truncation. `--gap` sets the
*minimum*; even distribution only ever adds to it.

`--separator` draws a **dashed cut line** centred in each gap, running the full
printable width from the left margin to the right margin. It is meant to be used
literally — a mark to align scissors against — not as decoration, so it is not
inset from the sheet edges the way a divider would be.

## Oversized blocks

A block taller than `usable` cannot fit any sheet in either mode. It is placed
alone on its own sheet, aligned to the top, and reported as clipped — on stderr
in CLI mode, as a badge on the row in the GUI. The `oversized.pdf` fixture
(826 pt of ink on an 841.889 pt page) exercises this.

## Worked example — the fixtures

A4 sheet (841.889 pt), margin 28, minimum gap 20, so `usable = 785.889`.

**Ordered, the `statement-*` fixtures.** Detected heights 163, 243, 313, 193, 273:

    sheet 1: 163 + 20+243 + 20+313 = 759  <= 785.889
             adding 193 would need 972    -> break
    sheet 2: 193 + 20+273 = 486

**Two sheets, 3 + 2** — five documents onto two sheets, three saved.

**Reordering, the `packing-*` fixtures.** Detected heights 403, 513, 353:

    ordered:   403 | 513 | 353                 -> 3 sheets
               (403+20+513 = 936 > usable, and 513+20+353 = 886 > usable)
    reordered: 513 | 403 + 20+353 = 776        -> 2 sheets

The lower bound is `ceil((403+513+353+2*20) / 785.889) = 2`, which the reordered
packing achieves, so it is provably optimal and no search is needed.

## Acceptance criteria

- The five `statement-*` fixtures produce exactly 2 sheets, 3 blocks then 2, in
  input order.
- The three `packing-*` fixtures produce 3 sheets by default and 2 sheets with
  `--reorder`, and the run reports the sheet saved.
- No block on any sheet overlaps another, and none crosses a margin.
- In ordered mode the block sequence in the output matches the input sequence
  exactly.
- In reordered mode the output contains every input block exactly once — a
  packer that loses or duplicates a block is the one failure that must never
  escape, so it is asserted on every packing test.
- Given N blocks that each exceed half the usable height, both modes produce
  exactly N sheets.

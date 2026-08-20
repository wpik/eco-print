# UC-05 — Automatic content-height detection

**Actor:** the tool itself, in both CLI and GUI mode.
**Goal:** decide, without asking anyone, which part of a source page is worth
printing.

## Why a heuristic is needed

A PDF does not record "where the content is". It records drawing operations. A
page whose text stops a third of the way down is, structurally, indistinguishable
from a full page — unless something measures the result.

## Method

Detection works on a **rendered raster** of the page rather than the object
model. Rasterising is immune to the tricks that break object inspection: white
rectangles drawn over content, off-page objects, clipped XObjects, vector
graphics, scanned images.

1. **Render** the page to greyscale at a low working resolution (72 dpi is
   enough; 1 px = 1 pt). Rendering is the only expensive step, and the result is
   cached per page for the GUI's live updates.
2. **Binarise** against a near-white threshold, so faint background tints and
   JPEG noise do not count as ink.
3. **Project** ink onto the vertical axis: for every row, does it contain any ink
   pixel? This yields the set of *ink rows*.
4. **Ignore page-edge artefacts.** Scan borders and full-width rules touching the
   very edge of the sheet are discarded before the next step.
5. **Group** consecutive ink rows into *bands*, merging bands separated by less
   than a small tolerance (a few points — ordinary line spacing).
6. **Cut at the largest gap.** Find the biggest whitespace gap between bands. If
   it is large enough to be structural, keep everything above it and discard the
   rest. This is what removes a trailing legal footer or page number.
7. **Pad** the kept region by `--pad` points on each side so descenders and
   antialiasing are not shaved, and clamp to the page box.
8. **Map** the pixel rectangle back to PDF points and store it as the block's
   content box.

## The largest-gap rule, stated precisely

Let the gaps between consecutive bands be g₁..gₙ, and let g\* be the largest.
The cut is taken at g\* only when **both** hold:

- g\* is at least a meaningful fraction of the page height — structural, not line
  spacing; and
- the ink discarded below the cut is a **small** minority of the page's total ink
  (a footnote's worth, not a section's worth).

Otherwise the tool falls back to the **full ink bounding box** — top of the first
band to bottom of the last. The second condition is the safety valve: it stops
the rule from amputating a document whose real content resumes after a large
gap, because there the discarded part is not a small trailing note.

Both fixtures that probe this rule are in `tests/data/`:

- **`with-footer.pdf`** — a 200 pt band, a 520 pt gap (62% of the page), then a
  two-line footer. The gap is structural and the footer is a few percent of the
  ink, so the cut is taken and the block is the 200 pt band plus padding.
- **`two-blocks.pdf`** — two 260 pt bands separated by a 220 pt gap. The gap is
  structural, but the lower band is half the page's ink, so the safety condition
  refuses the cut and the block spans both bands.

The pair is deliberate: they differ in what the rule must decide, not in whether
a gap exists. Any change to the thresholds has to keep both verdicts.

## Special cases

- **A blank page** — no ink at all — yields no block and is skipped, with a note
  in verbose output. It is not an error.
- **A full page of text** has no structural gap; the fallback keeps the whole ink
  box, and the block simply occupies a full sheet. The tool never makes a
  document worse than printing it directly.
- **Landscape or unusual page sizes** are detected the same way; the block keeps
  its own width and is placed on the output sheet at original scale.
- `--full-ink` skips steps 5–6 entirely and always uses the ink bounding box, for
  users who never want boilerplate dropped.

## Acceptance criteria

- Each `statement-*` fixture detects a block matching its generated ink height
  plus padding: 163, 243, 313, 193 and 273 pt at the default `--pad 6`.
- `with-footer.pdf` drops its footer; `two-blocks.pdf` keeps both bands.
- `full-page.pdf` has no structural gap and keeps its whole 761 pt ink box.
- `blank.pdf` produces no block and no crash.
- `landscape.pdf` and every page of `multipage.pdf` are detected independently
  and correctly.
- Detection of a single page completes fast enough to feel instantaneous in the
  GUI when a file is dropped.

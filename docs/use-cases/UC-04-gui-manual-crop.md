# UC-04 — GUI: adjust the crop manually

**Actor:** a GUI user whose document defeats automatic detection, or who wants
to keep or drop more than the tool chose.
**Goal:** set precisely which part of a page is printed.

This use case exists because auto-detection is a heuristic
([UC-05](UC-05-automatic-content-detection.md)). It is the escape hatch that
makes the heuristic safe to be aggressive.

## Main flow

1. The user selects a row in the document list. The preview renders that page in
   full, with the region outside the current crop dimmed.
2. The crop region is drawn as a rectangle with draggable **top and bottom
   edges**. The user drags an edge; the dimmed area follows in real time.
3. While dragging, a readout shows the region's height in points and millimetres,
   and the status line re-estimates the sheet count live — the user sees the cost
   of keeping the footer before committing to it.
4. Releasing the edge marks that page as **manually cropped**: its row shows a
   pencil badge and the `auto` checkbox for that page clears.
5. The user presses `Save PDF`. Manual boxes are used verbatim; untouched pages
   keep their automatic boxes.

## Interaction details

- **Snapping.** While dragging, an edge snaps to nearby ink boundaries (the top
  or bottom of a detected text band) within a few points, so a clean cut between
  two paragraphs needs no precision. Holding `Alt` suppresses snapping.
- **Reset.** `Reset to auto` restores the detected box for the current page;
  `Reset all` does so for every page.
- **Horizontal cropping** is not offered. Blocks span the full sheet width; a
  narrower block would not fit more per sheet, so it would cost the user
  precision for no paper saved.
- **Keyboard.** Arrow keys nudge the active edge by 1 pt, `Shift`+arrow by 10 pt.
- **Apply to all.** For a batch of identically laid-out documents — the common
  case — a `Apply this crop to all pages` action copies the current box to every
  page of the same source dimensions.

## Rules

- A crop may not be inverted or empty; the bottom edge cannot pass the top edge,
  and a minimum height of a few points is enforced.
- A crop may extend to the full page. Choosing to keep everything is allowed.
- A manual crop taller than the printable area of one sheet is accepted but
  flagged: that block will occupy a sheet of its own and be clipped at the
  bottom. The warning states this plainly before saving.
- Manual choices survive reordering and are lost only when the row is removed.

## Acceptance criteria

- Dragging the bottom edge of one page down to include the legal footer changes
  that page's height in the list and, if it pushes the total past a sheet
  boundary, increments the sheet count in the status line.
- `Reset to auto` restores exactly the height detection originally reported.
- `Apply this crop to all pages` gives every page in the list an identical
  height, whatever their detected heights were.

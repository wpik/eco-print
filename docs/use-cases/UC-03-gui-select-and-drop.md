# UC-03 — GUI: select and drag & drop inputs

**Actor:** a user who does not want to use a terminal.
**Goal:** assemble a compacted PDF visually.

## Trigger

`eco-print` run with **no arguments** opens the GUI. Any positional argument
means CLI mode ([UC-01](UC-01-cli-merge-explicit-files.md)); the two never mix.
`eco-print --gui FILE ...` opens the GUI pre-loaded with those inputs.

## Window layout

    +--------------------------------------------------------------+
    |  eco-print                                                    |
    +-------------------+------------------------------------------+
    |  Documents        |   Preview                                |
    |                   |                                          |
    |  [1] statement-a  |   +----------------------------------+   |
    |      p1  163pt    |   |                                  |   |
    |  [2] statement-b  |   |   rendered page with the crop    |   |
    |      p1  243pt    |   |   region highlighted and a       |   |
    |  [3] statement-c  |   |   draggable bottom edge          |   |
    |      p1  313pt    |   |                                  |   |
    |                   |   +----------------------------------+   |
    |  drop PDFs here   |   [x] auto   [ reset to auto ]           |
    +-------------------+------------------------------------------+
    |  Settings                                        [v] expand   |
    |   margin [ 28] gap [ 20] pad [  6]  size [ A4  v]             |
    |   [ ] keep footers and page numbers                           |
    |   [ ] rule between documents                                  |
    |   [ ] minimise pages (ignore order)                           |
    |   [ ] scan folders recursively        [ Reset to defaults ]   |
    +--------------------------------------------------------------+
    |  Output: [ ~/Documents/combined.pdf        ] [Browse]         |
    |  Result: 5 blocks -> 2 pages (saves 3 sheets)   [ Save PDF ]  |
    +--------------------------------------------------------------+

The settings block is collapsed by default — the tool must be usable by dropping
files and pressing save, without reading anything. It holds the full set of
options, which is exactly the set the CLI offers ([UC-08](UC-08-settings-parity.md)).

## Main flow

1. The user starts the GUI. The document list is empty and `Save PDF` disabled.
2. The user adds documents by any of:
   - dragging files from the file manager onto the window;
   - dragging a **folder**, which is expanded by the rules of [UC-02](UC-02-cli-directories.md);
   - the `Add files…` button, opening a native file dialog with multi-select.
3. Each added page appears in the list as a row with its thumbnail, source file
   name, page number, and detected block height. Detection runs automatically on
   add ([UC-05](UC-05-automatic-content-detection.md)); the user need not touch it.
4. Selecting a row shows that page in the preview with its crop region marked.
5. The user may reorder rows by dragging, and remove a row with `Delete`. Output
   order follows list order.
6. The live status line recomputes the sheet count after every change, so the
   effect of an edit on paper use is visible immediately.
7. Optionally the user opens **Settings** and adjusts any option — margins, gap,
   padding, sheet size, footer handling, separators, recursion, and
   **minimise pages (ignore order)**, the equivalent of `--reorder`
   ([UC-06](UC-06-page-packing.md)). Every change updates the status line at
   once, so the effect of an option on paper use is visible before committing to
   it; ticking minimise-pages when it would save nothing says so rather than
   silently changing nothing. The full mapping is [UC-08](UC-08-settings-parity.md).
8. The user sets the output path and presses `Save PDF`.
9. On success a confirmation appears with the final sheet count and a button to
   reveal the file in the file manager.

## Rules

- Dropping a file that is already in the list adds a second, independent entry.
  Printing the same document twice is a legitimate wish.
- Non-PDF drops are rejected with a message naming the ignored files; the valid
  PDFs in the same drop are still added.
- A password-protected file that cannot be opened is listed with an error badge
  and excluded from the output; it never blocks the rest of the batch.
- Adding a large number of files keeps the UI responsive: detection runs off the
  UI thread, and rows fill in progressively.

## Acceptance criteria

- Dragging a folder of the five `statement-*` fixtures onto the window produces
  five rows and a status line reading `2 pages`.
- `Save PDF` yields a file identical in layout to the CLI result for the same
  inputs and settings.
- Closing the window with unsaved documents asks for confirmation.

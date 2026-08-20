# UC-03 — GUI: select and drag & drop inputs

**Actor:** a user who does not want to use a terminal.
**Goal:** assemble a compacted PDF visually.

## Trigger

`eco-print` run with **no arguments** opens the GUI. Any positional argument
means CLI mode ([UC-01](UC-01-cli-merge-explicit-files.md)); the two never mix.
`eco-print --gui FILE ...` opens the GUI pre-loaded with those inputs.

## Window layout

    +--------------------------------------------------------------------------+
    |  eco-print                                                                |
    +-------------------+------------------------------------+-----------------+
    |  Documents        |   Preview                          |  Details        |
    |                   |                                    |  (hidden unless |
    |  [1] statement-a  |   +----------------------------+   |   "show detec-  |
    |      p1  163pt    |   |                              |   |   tion details"|
    |  [2] statement-b  |   |   rendered page with the    |   |   is ticked)    |
    |      p1  243pt    |   |   crop region highlighted   |   |                 |
    |  [3] statement-c  |   |   and a draggable bottom    |   |  statement-a p1 |
    |      p1  313pt    |   |   edge                      |   |   163pt kept    |
    |                   |   +----------------------------+   |   (ink-box)     |
    |  drop PDFs here   |   [x] auto   [ reset to auto ]     |  statement-b p1 |
    +-------------------+------------------------------------+   243pt kept    |
    |  Settings                                        [v] expand              |
    |   margin [ 28] gap [ 20] pad [  6]  size [ A4  v]                        |
    |   [ ] keep footers and page numbers                                     |
    |   [ ] add horizontal line between documents                             |
    |   [ ] minimise pages (ignore order)                                     |
    |   [ ] scan folders recursively                                          |
    |   [ ] show detection details          [ Reset to defaults ]             |
    +--------------------------------------------------------------------------+
    |  Output: [ ~/Documents/combined.pdf        ] [Browse]                    |
    |  Result: 5 blocks -> 2 pages (saves 3 sheets)     [Copy cmd] [Save PDF]   |
    |                                                              [   Exit  ]  |
    +--------------------------------------------------------------------------+

The settings block is collapsed by default — the tool must be usable by dropping
files and pressing save, without reading anything. It holds the full set of
options, which is exactly the set the CLI offers ([UC-08](UC-08-settings-parity.md)).

The one exception: if any remembered setting is not at its default when the
window opens — typically because a previous session changed and kept it — the
panel opens expanded instead. A non-default setting has already told the tool
it matters to this user, and hiding it behind a click would surprise them more
than showing it does.

The **Details** pane is the GUI's rendering of `--verbose`
([UC-08](UC-08-settings-parity.md)): what each page's detection decided and why,
what was skipped and why, and the packing outcome sheet by sheet. It is hidden by
default and appears only while "show detection details" is ticked, so it costs
nothing to a user who never asks for it.

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
8. Optionally the user ticks **show detection details**, which opens the
   Details pane: a running account of what was kept, what was dropped and by
   which method, any inputs that were skipped and why, and the sheet-by-sheet
   packing outcome. It updates with every change to the list or the settings,
   the same way the status line does.
9. The user sets the output path and presses `Save PDF`.
10. On success a dialog reports the final sheet count and offers three choices:
    **Open Document** opens the written PDF in the system's default viewer and
    closes the dialog; **Open Folder** opens the folder containing it and
    closes the dialog; **Close** dismisses the dialog with no further action.
    This save is also what stops the window asking to confirm on close
    ([UC-03 close behaviour](#closing-the-window)).

## Rules

- Dropping a file that is already in the list adds a second, independent entry.
  Printing the same document twice is a legitimate wish.
- Non-PDF drops are rejected with a message naming the ignored files; the valid
  PDFs in the same drop are still added.
- A password-protected file that cannot be opened is listed with an error badge
  and excluded from the output; it never blocks the rest of the batch.
- Adding a large number of files keeps the UI responsive: detection runs off the
  UI thread, and rows fill in progressively.

## Closing the window

Closing must not interrupt a user who has nothing to lose, but must not lose
real work either. The window tracks whether the current state has been written
out:

- Adding, removing or reordering documents, editing a crop, or changing a
  setting all mark the session **modified**.
- A successful `Save PDF` marks it **saved**, against the exact state that was
  written.
- Closing prompts for confirmation only when the session is **both** modified
  *and* has not been saved since — an empty window, and a window whose current
  state was just written to disk, close immediately.
- Making a further change after a save re-arms the prompt: the state on disk no
  longer matches what is on screen.

An **Exit** button sits directly below `Save PDF`, on its own row, and closes
the window the same way the window's own close control does, so it is subject
to the same confirmation — an Exit button that skipped the check would be a
second, inconsistent way to quit.

## Acceptance criteria

- Dragging a folder of the five `statement-*` fixtures onto the window produces
  five rows and a status line reading `2 pages`.
- `Save PDF` yields a file identical in layout to the CLI result for the same
  inputs and settings.
- Closing an empty window, or a window whose current state was just saved,
  closes without a prompt.
- Adding a document, editing a crop, or changing a setting after a save
  re-arms the confirmation on close.
- `Exit` and the window's own close button behave identically with respect to
  the confirmation.
- Ticking "show detection details" opens the Details pane with content; the
  panel is not merely present but reports what was actually kept and dropped.
- After a successful save, choosing **Open Document** opens the written file
  and the dialog closes; choosing **Open Folder** opens its containing
  directory and the dialog closes; choosing **Close** opens nothing and the
  dialog simply closes.
- Opening the window with every setting at its default leaves the Settings
  panel collapsed; opening it with any one setting remembered away from its
  default leaves the panel expanded.
- `Exit` renders on its own row, below `Save PDF`.

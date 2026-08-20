# Implementation plan

Companion to the [use cases](use-cases/). This describes *how* the tool gets
built; the use cases define *what* it must do.

## 1. Technology choices

| Concern | Choice | Why |
| --- | --- | --- |
| Language | Python 3.11+ | Available; `tomllib` and modern typing in stdlib. |
| Environment | `venv` at `.venv/`, `pyproject.toml` | Requested. No global installs. |
| Page rendering | **pypdfium2** | Google's PDFium, the Chrome engine. Permissive licence, fast, self-contained wheels, no Ghostscript subprocess. |
| Raster analysis | **Pillow** + **NumPy** | Row projection is one vectorised operation. |
| PDF composition | **pypdf** | Pure Python, BSD. Decrypts empty-user-password files, crops via the page boxes, and places blocks with `merge_transformed_page`. Verified against the fixtures. |
| GUI | **PySide6** | Native drag & drop, `QGraphicsView` for the crop editor. |
| CLI | `argparse` | Stdlib is sufficient for one positional list and a dozen flags. |
| Tests | `pytest` | Against the generated fixture corpus in `tests/data/`. |

**Licence note.** The obvious alternative is PyMuPDF, which does rendering *and*
composition in one library and would remove two dependencies. It is **AGPL-3.0**,
which is contagious if the tool is ever distributed. pypdfium2 + pypdf keeps the
project permissively licensed at the cost of one extra dependency. Say the word
if you would rather have the simpler dependency graph and don't care about AGPL.

## 2. Repository layout

    eco-print/
      pyproject.toml            # metadata, deps, [gui] extra, console_scripts
      README.md
      .venv/                    # git-ignored
      docs/
        README.md
        implementation-plan.md
        use-cases/UC-01..UC-07
      src/eco_print/
        __init__.py
        settings.py             # UC-08 Options: the single declaration of every option
        model.py                # Block, ContentBox, Sheet, PackResult
        loader.py               # inputs -> source pages (files, dirs, decryption)
        detect.py               # UC-05 content detection
        packer.py               # UC-06 ordered packing, layout, PackResult
        repack.py               # UC-06 reordered packing (--reorder)
        pipeline.py             # load -> detect -> pack -> compose, front-end agnostic
        compose.py              # writes the output PDF
        cli.py                  # UC-01, UC-02
        gui/
          __init__.py           # optional-extra guard
          state.py              # the document list and crops, with no Qt in it
          app.py                # window, document list, wiring
          settings_panel.py     # UC-08 panel, generated from Options
          cropview.py           # UC-04 interactive crop editor
          droparea.py           # UC-03 drag & drop
          cropview.py           # UC-04 interactive crop editor
          worker.py             # detection off the UI thread
      tests/
        data/
          generate_fixtures.py  # regenerates the corpus; no dependencies
          *.pdf                 # the committed fixtures
        test_detect.py test_packer.py test_repack.py test_loader.py
        test_compose.py test_cli.py test_fixtures.py
        test_settings.py test_settings_parity.py
        test_gui_state.py test_gui_widgets.py

The core (`loader` → `detect` → `packer` → `compose`) has **no GUI import**. The
GUI is an optional extra: `pip install -e .` gives a working CLI without Qt;
`pip install -e '.[gui]'` adds it. CLI users should not need a 100 MB download.

## 3. Options

Every option is declared once, in `settings.py`, as a dataclass whose fields
carry their own flag name, type, default, range, help text and GUI control kind
(UC-08). The argparse parser and the Qt settings panel are both **built by
walking those fields**, so an option cannot exist in one front end and not the
other, and the help text cannot disagree between them.

`Options` is also the only thing the pipeline takes besides its inputs: `detect`
reads `pad` and `full_ink`, `packer` reads `margin`, `gap`, `page_size` and
`reorder`, `compose` reads `separator`. Nothing reads argparse or Qt.

Because both front ends produce the same `Options` object, "same inputs and
settings give byte-identical output" is not a coincidence to be maintained — it
is the only thing that can happen.

## 4. Data model

    ContentBox  = source page rect to keep, in PDF points, plus `origin`
                  ("auto" | "manual" | "full-ink")
    Block       = source path, page index, page size, ContentBox
                  -> width/height derived from the box
    Sheet       = list of (Block, y-offset), given a sheet size
    PackResult  = sheets + counters for the summary line, including the sheet
                  count the *other* packing mode would have produced

Everything downstream of `detect` speaks `Block`. That is what lets the GUI
override a box (UC-04) by swapping one field and re-running the packer, with no
special case anywhere else.

## 5. Milestones

Each milestone ends with something runnable and its tests green.
Status: **all milestones, including M7, are implemented** on
`feature/initial-version`. on `feature/initial-version`; M3 onwards
are not started.

**M1 — Skeleton, environment and options.** *(done)* `pyproject.toml`, `.venv`, package
layout, `eco-print --version` on the path, and `settings.py` with the full
`Options` declaration (UC-08). Declaring the options first means every later
milestone consumes them rather than inventing its own arguments.
*Done when:* a fresh clone reaches a working console command in two commands, and
`--help` lists every option from the dataclass.

**M2 — Loader.** *(done)* Files, directories, `--recursive`, name sorting, output-path
exclusion, empty-password decryption, per-source error isolation (UC-02, UC-07).
*Done when:* the five encrypted samples load as five source pages, and a renamed
JPEG among them is skipped by name rather than crashing.

**M3 — Detection.** *(done)* Render at 72 dpi, binarise, project, band, largest-gap rule
with the safety condition, padding, `--full-ink` (UC-05). *Done when:* all five
samples report 228 ± 2 pt, a synthetic two-block page keeps both blocks, and a
blank page yields none.

**M4a — Ordered packer and composition.** *(done)* Greedy pass, even leftover
distribution, oversized-block handling, `--separator`; output written with pypdf
(set the four page boxes, drop `/Annots`, `merge_transformed_page` with a
translation). (UC-06)
*Done when:* the five `statement-*` fixtures produce a 2-page PDF, blocks 3 + 2,
at 1:1 scale.

**M4b — Reordered packer (`--reorder`).** *(done)* Lower bound, First-Fit-Decreasing,
branch-and-bound under a time budget, tallest-first emission within a sheet, and
the "saved N sheets" reporting. Shares everything downstream with M4a — it
returns the same `PackResult`, so composition needs no changes. (UC-06)
*Done when:* the three `packing-*` fixtures give 3 sheets by default and 2 with
`--reorder`; and a randomised test over many height sets asserts that the
reordered count is never worse than the ordered one and never below the lower
bound.

**M5 — CLI.** *(done)* Parser **generated from `Options`**, positional inputs and output,
`--dry-run`, summary line, exit codes, refusing to overwrite (UC-01, UC-08).
*Done when:* pointing the tool at the fixture directory prints
`5 blocks from 5 documents -> 2 pages` and the acceptance criteria of UC-01 and
UC-02 hold end to end.

**M6 — GUI.** *(done)* Window and list, drag & drop of files and folders, background
detection, live sheet-count status, output picker and save (UC-03); the settings
panel **generated from `Options`**, with live recomputation and persistence
between sessions (UC-08); then the crop editor: dimmed overlay, draggable edges,
snapping, reset, apply-to-all (UC-04).
*Done when:* dropping the fixture folder shows five rows and `2 pages`; saving
matches the CLI output byte for byte; and the parity test passes with every
option present in the panel.

A useful CLI exists from M5 — before any Qt code is written. If the GUI proves
fiddly, the paper-saving is already in hand.

**M7 — GUI polish from first real use.** *(done)*

- The separator becomes a **dashed cut line** spanning margin to margin, not a
  filled decorative bar, and its label changes to "add horizontal line between
  documents" (UC-06, UC-08).
- The **Details pane** is built and wired to `Session`: a third column, hidden
  unless "show detection details" is ticked, showing the same per-page report
  `-v` gives the CLI. This is what "show detection details" was supposed to do
  from M6 — the checkbox existed and toggled `Options.verbose`, but nothing
  consumed the value, so it had no visible effect (UC-03, UC-08).
- **Close confirmation** becomes conditional: `Session` tracks a `revision`
  counter bumped by every mutation (add, remove, move, crop, apply-options) and
  a `saved_revision` set on a successful write. The window prompts only when
  they differ and the list is non-empty, so an untouched or just-saved window
  closes immediately, and any further edit re-arms the prompt (UC-03).
- An **Exit** button is added beside `Save PDF`, calling the same close path as
  the window's own close control so it is subject to the same confirmation
  (UC-03).
- **UC-08 strengthened**: parity was previously tested only as reachability
  (every field has a flag and a widget). A second check now asserts each
  field's *documented effect* actually happens — this is the gap that let
  "show detection details" ship inert, and the new test is written to catch
  exactly that shape of bug again.

*Done when:* the separator prints as a dashed line at each margin; ticking
"show detection details" populates the Details pane with real content; closing
an unmodified or freshly-saved window is silent while closing a modified one
prompts; `Exit` behaves identically to the window's close button; and the
strengthened parity test passes for every option, `verbose` included.

## 6. Testing strategy

- **Generated corpus.** `tests/data/generate_fixtures.py` writes minimal PDFs
  directly, with no dependencies, and is committed alongside its output. Every
  fixture pins its ink extent with hairline rules at the exact top and bottom of
  each band, so tests assert detected heights against numbers the generator
  chose rather than against whatever a text renderer happened to produce. No
  real document, and no personal data, is in the repository.
- The corpus covers each branch the code has: differing heights for packing,
  a droppable footer and a non-droppable second block for the detection rule,
  a blank page, a full-text page, landscape geometry, a multi-page document, an
  oversized block, and an encrypted file with an empty user password.
- **Regeneration is part of CI:** running the generator must leave the committed
  fixtures byte-identical, so the corpus cannot silently drift from its
  description. `encrypted.pdf` is exempt from the byte check and compared by
  content instead — pypdf happens to produce it deterministically today, but
  nothing in its contract promises that across versions.
- **Round-trip assertions** rather than byte comparison of output PDFs: re-render
  the produced sheets and assert that ink appears where the packer said it would,
  and that no ink from a discarded region survived.
- **The headline tests:** five files in, two pages out, blocks 3 + 2; and the
  three packing fixtures going from 3 sheets to 2 under `--reorder`. They are the
  requirements, so they are tests.
- **Packer invariants**, asserted on every packing test in both modes: every
  input block appears in the output exactly once, no sheet exceeds its usable
  height, and the reordered count is never worse than the ordered count.
- **Parity is tested structurally, not by review** (UC-08). `test_settings_parity`
  enumerates the fields of `Options` and asserts each is reachable from the
  generated parser and from the panel definition, and that the list of flags
  satisfied by GUI behaviour rather than a control is exactly the documented
  three. Adding an option without wiring it up fails the suite.
- **Cross-front-end equivalence:** for several settings combinations, the same
  inputs are run through the CLI and through the GUI's controller with the same
  `Options`, and the two outputs must be byte-identical.
- GUI logic is tested through the core; only trivial glue lives in Qt classes,
  and no test needs a display server.

## 7. Risks

| Risk | Mitigation |
| --- | --- |
| The largest-gap rule cuts real content on some document | Safety condition in UC-05, `--full-ink` escape, and the GUI's manual crop. Verbose mode always reports what was dropped. The `two-blocks.pdf` fixture guards the threshold. |
| pypdf composition trips over another malformed input | Annotations already dropped; per-source error isolation keeps a batch alive. |
| PySide6 install weight annoys CLI-only use | GUI is an optional extra, not a hard dependency. |
| Rendering large batches is slow | 72 dpi is cheap; detection streams page by page and the GUI runs it off-thread. |
| Exact bin-packing search blows up on a large batch | It runs only after FFD misses the lower bound, only below a block-count ceiling, and under a time budget; the FFD result is always available as a fallback. |
| Reordering surprises a user whose document order mattered | Off by default, named "ignore order" in the GUI, and the summary always states how many sheets it actually saved. |
| Options drift apart between the CLI and the GUI | They cannot: both are generated from one dataclass, and the parity test fails on any gap (UC-08). |
| A settings panel makes the GUI intimidating | The block is collapsed by default; the tool works by dropping files and pressing save. |
| Scope creep into a general imposition tool | The use cases fix the scope: vertical stacking, full width, no scaling. |

## 8. Open questions

1. **Project path.** You wrote `/wpik/workspace/eco-printo-print` for the code and
   `/Users/wpik/workspace/eco-print` for the docs. Only the latter exists, so
   everything is going there. Correct if that is wrong.

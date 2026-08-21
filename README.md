## eco-print

Extract the meaningful part of each PDF page and re-pack those parts onto as few
sheets as possible.

Documents from banks, ticketing systems and government portals routinely put a
few centimetres of content on an A4 page and leave the rest blank. Printing five
of them costs five sheets. eco-print finds the content, drops the boilerplate,
and stacks what is left:

    $ eco-print ~/statements combined.pdf
    5 blocks from 5 documents -> 2 pages (saved 3 sheets)
    wrote combined.pdf

Nothing is scaled — a distance on the output equals the same distance on the
source, so the result prints exactly as legibly as the originals.

### Install

No Python at all: download the executable for your platform from the
[Releases](../../releases) page and run it. It opens the GUI with no
arguments, or works as the CLI documented below when given some -- one file,
same tool either way (see [UC-09](docs/use-cases/UC-09-native-executables.md)
for how it's built and its one platform-specific quirk, the Windows console).

Or, with Python 3.11 or newer, in a virtual environment:

    python3 -m venv .venv
    ./.venv/bin/pip install -e .

That gives you the command line. The graphical interface needs Qt, which is an
optional extra so that command-line users are not made to download 100 MB of it:

    ./.venv/bin/pip install -e '.[gui]'

### Command line

The last argument is always the output; everything before it is an input. Inputs
may be files or directories, mixed freely, and are processed in the order given:

    eco-print invoice.pdf receipt.pdf out.pdf
    eco-print ~/scans out.pdf
    eco-print ~/scans/january ~/scans/february extra.pdf quarter.pdf

| Option | Effect |
| --- | --- |
| `--margin PT` | Outer margin of the sheet. Default 28. |
| `--gap PT` | Minimum space between blocks. Default 20. |
| `--pad PT` | Whitespace kept around the detected content. Default 6. |
| `--page-size` | `a4` (default) or `letter`. |
| `--full-ink` | Keep the whole ink area; never drop trailing footers. |
| `--separator` | Draw a dashed cut line between blocks on a sheet, margin to margin. |
| `--reorder` | Give up input order in exchange for the fewest possible sheets. |
| `--recursive` | Descend into subdirectories of directory inputs. |
| `--force` | Overwrite an existing output file. |
| `--dry-run` | Report what would be produced, and write nothing. |
| `-v`, `--verbose` | Say what was detected and what was dropped, page by page. |

Exit codes distinguish a clean run (`0`) from one that skipped an input (`1`)
from one that produced nothing (`2`), so a script can tell the difference while a
person still gets a usable document.

### Graphical interface

Run `eco-print` with no arguments. Drop PDFs or folders onto the window, watch
the sheet count update as you go, and press **Save PDF**.

Detection runs automatically, but the preview lets you drag the crop edges
yourself when a document defeats it — edges snap to ink boundaries, and one
adjustment can be copied across a batch of identically laid-out documents.

Everything the command line can do, the window can do too: the options are
declared once in the code and both front ends are generated from that
declaration. **Copy as command line** hands you the invocation matching your
current settings, so you can tune by eye and then automate.

### How it decides what to keep

A PDF does not record where its content is — only drawing operations. So
eco-print renders each page and measures the result, which is immune to white
rectangles painted over content, off-page objects and scans.

Ink rows are grouped into bands, and the page is cut at the largest whitespace
gap — but only when that gap is structural **and** what falls below it is a small
minority of the page's ink. Without that second condition, a document whose real
content resumes lower down would be amputated. When the rule does not apply, the
whole ink area is kept, so eco-print never makes a document worse than printing
it directly.

Blocks are then stacked in input order, breaking to a new sheet whenever the next
one does not fit. With order fixed that greedy pass is optimal. `--reorder` lifts
the constraint and solves the bin-packing problem instead: a lower bound first,
so a provably optimal packing stops the work immediately, then
First-Fit-Decreasing, then an exact search for small batches under a time budget.

### Development

    ./.venv/bin/pip install -e '.[gui,dev]'
    ./.venv/bin/python -m pytest

The test fixtures in `tests/data/` are synthetic PDFs written by
`tests/data/generate_fixtures.py`, which has no dependencies. Each one pins its
ink extent exactly, so tests assert detected heights against numbers the
generator chose. No real document, and no personal data, is in this repository.
A test asserts that regenerating the corpus reproduces the committed bytes, so it
cannot drift from what the documentation says it contains.

`docs/` holds the [use cases](docs/use-cases/) the tool is built against.

### Building a native executable

    ./.venv/bin/pip install -e '.[gui,packaging]'
    cd packaging
    pyinstaller --noconfirm eco-print.spec
    python smoke_test.py

Builds only for the platform you run it on -- PyInstaller does not
cross-compile. `.github/workflows/build.yml` builds all three platforms on a
version tag or on demand; see [UC-09](docs/use-cases/UC-09-native-executables.md).

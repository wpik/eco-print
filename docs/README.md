# eco-print — documentation

`eco-print` extracts the meaningful content area from PDF pages and re-packs those
areas onto as few sheets of paper as possible. Its purpose is to save paper when
printing documents that use only a fraction of each page — bank transfer
confirmations, receipts, tickets, invoices.

## Vocabulary

| Term | Meaning |
| --- | --- |
| **source page** | One page of one input PDF. |
| **block** | The cropped, meaningful region of a source page. One source page yields exactly one block. |
| **content box** | The rectangle, in PDF points, describing a block's extent within its source page. |
| **sheet** | One output page onto which several blocks are placed. |
| **packing** | Deciding which blocks go on which sheet, and where. |

## Design decisions

These are settled; they are the assumptions the use cases are written against.

1. **GUI toolkit is PySide6 (Qt).** Native drag & drop and page rendering.
2. **Auto-detection drops trailing boilerplate** using the largest-gap rule
   (see [UC-05](use-cases/UC-05-automatic-content-detection.md)).
3. **Every page of every input is its own block.** Multi-page inputs are not
   truncated to the first page.
4. **Blocks are never scaled.** A block that does not fit the remaining space
   starts a new sheet. Text stays at 1:1.
5. **Input order is preserved by default**, and may be given up explicitly with
   `--reorder` to reach the true minimum sheet count
   ([UC-06](use-cases/UC-06-page-packing.md)).
6. **The CLI and the GUI expose the same options.** They are declared once and
   both front ends are generated from that declaration
   ([UC-08](use-cases/UC-08-settings-parity.md)).
7. **Python with a virtual environment.** No global installs.

## Implementation

See [implementation-plan.md](implementation-plan.md).

## Use cases

| ID | Title |
| --- | --- |
| [UC-01](use-cases/UC-01-cli-merge-explicit-files.md) | CLI — merge an explicit list of files |
| [UC-02](use-cases/UC-02-cli-directories.md) | CLI — process directories |
| [UC-03](use-cases/UC-03-gui-select-and-drop.md) | GUI — select and drag & drop inputs |
| [UC-04](use-cases/UC-04-gui-manual-crop.md) | GUI — adjust the crop manually |
| [UC-05](use-cases/UC-05-automatic-content-detection.md) | Automatic content-height detection |
| [UC-06](use-cases/UC-06-page-packing.md) | Packing blocks onto the fewest sheets |
| [UC-07](use-cases/UC-07-difficult-inputs.md) | Difficult inputs and failure handling |
| [UC-08](use-cases/UC-08-settings-parity.md) | Every option available in both front ends |

## Reference corpus

The test suite works against a set of synthetic PDFs in `tests/data/`, produced
by `tests/data/generate_fixtures.py`. They are generated rather than collected so
that no real document — and no personal data — lives in the repository, and so
that every fixture's exact ink extent is a number the generator chose and the
tests can assert against.

| Fixture | Ink height | Purpose |
| --- | --- | --- |
| `statement-a..e.pdf` | 151, 231, 301, 181, 261 pt | Five ordinary documents of differing heights. The headline case: five inputs, two sheets. |
| `packing-a..c.pdf` | 391, 501, 341 pt | Chosen so ordered packing needs three sheets and reordered packing needs two ([UC-06](use-cases/UC-06-page-packing.md)). |
| `with-footer.pdf` | 200 pt band + trailing footer | The largest-gap rule must drop the footer. |
| `two-blocks.pdf` | two 260 pt bands, 220 pt apart | The safety condition must refuse the cut and keep both. |
| `full-page.pdf` | 761 pt | No structural gap; nothing may be dropped. |
| `blank.pdf` | none | Yields no block, and no crash. |
| `landscape.pdf` | 181 pt, landscape | Non-portrait source geometry. |
| `multipage.pdf` | 121, 301, 201 pt | Three pages of one document, each its own block. |
| `oversized.pdf` | 826 pt | Taller than a sheet's usable area. |
| `encrypted.pdf` | 231 pt | Owner password set, user password empty — must open without a prompt ([UC-07](use-cases/UC-07-difficult-inputs.md)). |

Regenerate at any time with:

    python tests/data/generate_fixtures.py

# UC-01 — CLI: merge an explicit list of files

**Actor:** a user at a terminal.
**Goal:** turn several PDFs into one PDF that uses fewer sheets of paper.

## Trigger

    eco-print FILE [FILE ...] OUTPUT

The last positional argument is always the output path. Everything before it is
an input. At least one input and one output must be given.

## Main flow

1. The user runs, from a folder of statements:

       eco-print statement-*.pdf combined.pdf

2. The tool expands the inputs into an ordered list of source PDFs. Shell
   globbing has already expanded the pattern, so the tool receives five paths.
3. For each source PDF, in the order given, it opens the file. Encrypted files
   with an empty user password are decrypted transparently ([UC-07](UC-07-difficult-inputs.md)).
4. For each page of each PDF, it determines the content box automatically
   ([UC-05](UC-05-automatic-content-detection.md)). No user interaction occurs.
5. It packs the resulting blocks onto the fewest sheets ([UC-06](UC-06-page-packing.md)).
6. It writes the output PDF to `combined.pdf` and prints a summary:

       5 blocks from 5 documents -> 2 pages (saved 3 sheets)
       wrote combined.pdf

7. Exit code is 0.

## Ordering

By default blocks appear in the output in input order: the order of the arguments
on the command line, and within one document, page order. Packing chooses page
breaks only — predictable output is worth more than an occasional extra sheet.

`--reorder` lifts that guarantee: blocks may be rearranged freely so that the
output uses the fewest sheets that exist for the given set
([UC-06](UC-06-page-packing.md)). This is the right choice for a pile of
unrelated receipts and the wrong one for a document whose sequence means
something.

## Alternate flows

- **Output path exists.** The tool refuses and exits non-zero unless `--force` is
  given, so an accidental overwrite of a source document is impossible.
- **Output path is also an input.** Refused unconditionally.
- **A single input.** Perfectly valid; one document is compacted on its own.
- **Everything fits on one sheet.** Normal outcome, one-page output.

## Options

| Flag | Effect |
| --- | --- |
| `--force` | Overwrite an existing output file. |
| `--recursive` | Descend into subdirectories of directory inputs ([UC-02](UC-02-cli-directories.md)). |
| `--margin PT` | Outer margin of the sheet. Default 28. |
| `--gap PT` | Minimum vertical space between blocks. Default 20. |
| `--page-size` | Output sheet size. Default `a4`; `letter` also accepted. |
| `--full-ink` | Disable footer dropping; keep the whole ink area ([UC-05](UC-05-automatic-content-detection.md)). |
| `--pad PT` | Extra whitespace kept around the detected content. Default 6. |
| `--reorder` | Give up input order in exchange for the fewest possible sheets. |
| `--separator` | Draw a dashed cut line between blocks on a sheet, margin to margin. |
| `--dry-run` | Report the detected boxes and the resulting sheet count; write nothing. |
| `-v/--verbose` | Per-page detection detail. |

Every one of these is also available in the GUI — see
[UC-08](UC-08-settings-parity.md), which is the authority on the mapping. The
options are declared once and both front ends are built from that declaration, so
this table cannot drift out of date.

## Acceptance criteria

- The five `statement-*` fixtures produce a **2-page** output.
- Every block is legible and complete: no glyph of the kept region is clipped.
- Blocks are at original scale — a distance measured on the output equals the
  same distance measured on the source.
- Re-running with the same inputs produces a byte-identical output.

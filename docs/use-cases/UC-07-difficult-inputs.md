# UC-07 — Difficult inputs and failure handling

**Actor:** the tool, in both modes.
**Goal:** never lose a batch because one file misbehaves, and never silently
produce a wrong document.

## Encrypted PDFs

Documents issued by banks, ticketing systems and government portals are commonly
encrypted with an owner password and an **empty user password**. Such files open
fine in any viewer, but naive libraries refuse them outright.

- The tool always attempts decryption with an empty password when a file reports
  as encrypted. This covers the overwhelming majority of such documents.
- A file needing a real password is reported as such. CLI: named on stderr and
  skipped. GUI: an error badge on the row, with a prompt to enter a password.
- Owner-password restrictions on printing or copying are **not** treated as a
  reason to refuse. The user already possesses the document.
- The output PDF is written unencrypted.

## Malformed structure

Real-world PDFs are frequently a little broken. Two defects seen repeatedly in
documents from production systems: a missing xref entry for the xref stream
itself, and page annotations lacking the `/Rect` entry the specification
requires — the latter crashes a straight page merge.

- Recoverable structural damage is repaired on load where the library allows it,
  and noted in verbose output only. Warnings that the user can do nothing about
  do not belong on a normal run's output.
- Annotations are **dropped** from extracted blocks. They are links and form
  widgets whose coordinates no longer mean anything after cropping and
  repositioning, and one bad annotation must not fail the run.

## Batch resilience

One bad file never aborts a batch:

- Each source is processed independently; a failure is recorded against that
  source and processing continues.
- The run summary reports what was skipped and why.
- The exit code is 0 if every input was processed, and non-zero if any input was
  skipped — so a script can tell a clean run from a partial one, while a person
  still gets the usable output.
- If **every** input fails, no output file is written at all. A zero-page PDF is
  worse than no PDF.

## Other cases

| Input | Behaviour |
| --- | --- |
| Not a PDF despite the extension | Skipped with a message naming the file. |
| Zero-page PDF | Skipped; no blocks. |
| Blank page inside a document | Skipped; other pages still contribute ([UC-05](UC-05-automatic-content-detection.md)). |
| Page sizes mixed within one run | Allowed. Each block keeps its own size; sheets are uniform. |
| Block wider than the output sheet | Placed at original scale, left-aligned within the margin, and reported as clipped at the right edge. |
| Very large batch | Handled; detection is streamed page by page rather than holding every raster in memory. |
| Output directory does not exist | Created if its parent exists; otherwise a clear error. |
| No write permission on the output | Clear error before any processing work is done. |

## Acceptance criteria

- An encrypted file with an empty user password processes without the user
  supplying anything.
- A batch of the five `statement-*` fixtures plus a renamed JPEG produces the
  2-sheet output from the valid five, names the bad file, and exits non-zero.
- A corrupt PDF never produces a traceback in the user's face; it produces a
  sentence.

# UC-02 — CLI: process directories

**Actor:** a user at a terminal.
**Goal:** compact every PDF in a folder without listing the files by hand.

## Trigger

Any positional input that is a directory rather than a file:

    eco-print ~/scans combined.pdf
    eco-print ~/scans/january ~/scans/february quarter.pdf
    eco-print ~/scans extra-receipt.pdf all.pdf

## Main flow

1. Each input is classified as a file or a directory.
2. A directory is expanded to the `*.pdf` files **directly inside it**. The scan
   is not recursive by default; `--recursive` descends into subdirectories.
3. Files within one directory are sorted by name, case-insensitively, so the
   result does not depend on filesystem order. This makes runs reproducible.
4. Directories and files may be mixed freely. The expansion of each argument is
   spliced into the input list at that argument's position, preserving the
   left-to-right order the user typed.
5. Processing continues exactly as in [UC-01](UC-01-cli-merge-explicit-files.md).

## Rules

- Non-PDF files in a directory are ignored silently. A directory of holiday
  photos with one PDF in it yields one block.
- Hidden files (leading `.`) are ignored.
- The output file is excluded from the inputs even when it sits inside a scanned
  directory. Without this, re-running the command in place would feed the
  previous result back in.
- A directory containing no PDFs is not an error by itself, but if the whole run
  finds zero source pages the tool exits non-zero with a clear message.

## Acceptance criteria

- Pointing the tool at a directory holding the five `statement-*` fixtures gives
  the same 2-page result as listing those files explicitly.
- Running the same command twice in a row, with the output inside the scanned
  directory, gives the same result both times.

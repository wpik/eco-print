"""The command-line front end (UC-01, UC-02).

The option flags are not written out here: `settings.add_options` generates them
from `Options`, which is what keeps the CLI and the GUI in step (UC-08). Only the
arguments that concern the run rather than the output are declared locally.

Milestones M1 and M2 are implemented: inputs resolve and load. Packing and
composition arrive with M4, and until then `main` reports what it loaded and
stops rather than pretending to write a document.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .loader import load
from .model import LoadResult
from .settings import Options, add_options

EXIT_OK = 0
EXIT_PARTIAL = 1        # produced output, but something was skipped
EXIT_FAILED = 2         # produced nothing

log = logging.getLogger("eco_print")


def build_parser() -> argparse.ArgumentParser:
    """The full command line: run arguments here, output options generated."""
    parser = argparse.ArgumentParser(
        prog="eco-print",
        description=(
            "Extract the content area of PDF pages and re-pack it onto fewer "
            "sheets of paper."
        ),
        epilog=(
            "The last positional argument is the output PDF; everything before "
            "it is an input file or directory. Run with no arguments for the "
            "graphical interface."
        ),
    )
    parser.add_argument(
        "paths", nargs="*", type=Path, metavar="INPUT",
        help="input PDFs and directories, followed by the output PDF",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="overwrite the output file if it already exists",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would be produced, and write nothing",
    )
    parser.add_argument(
        "--version", action="version", version=f"eco-print {__version__}",
    )
    add_options(parser)
    return parser


def split_paths(paths: list[Path]) -> tuple[list[Path], Path]:
    """Separate the trailing output path from the inputs.

    Raises `SystemExit` through the caller's error handling when the command
    line does not carry both.
    """
    if len(paths) < 2:
        raise ValueError(
            "give at least one input and an output path, "
            "for example: eco-print statements/ combined.pdf"
        )
    return paths[:-1], paths[-1]


def check_output(output: Path, force: bool, dry_run: bool) -> None:
    """Refuse an output that would destroy something, before doing any work."""
    if output.suffix.lower() != ".pdf":
        raise ValueError(f"output must be a .pdf file: {output}")
    if output.exists() and not force and not dry_run:
        raise ValueError(
            f"{output} already exists; pass --force to overwrite it"
        )
    parent = output.parent
    if not parent.exists() and not dry_run:
        if not parent.parent.exists():
            raise ValueError(f"no such directory: {parent}")
        parent.mkdir()


def report_load(result: LoadResult, verbose: bool) -> None:
    """Tell the user what was skipped, and — when asked — what was found."""
    for error in result.errors:
        print(f"skipped {error.path}: {error.reason}", file=sys.stderr)
    if verbose:
        for page in result.pages:
            print(f"  {page.label}: {page.width:.0f} x {page.height:.0f} pt")


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns the process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.paths:
        # No arguments at all means the GUI (UC-03). It arrives with M6.
        print(
            "eco-print: the graphical interface is not built yet (M6).\n"
            "Give input paths and an output path to use the command line, "
            "or run --help.",
            file=sys.stderr,
        )
        return EXIT_FAILED

    options = Options.from_namespace(args)
    logging.basicConfig(
        level=logging.DEBUG if options.verbose else logging.WARNING,
        format="%(message)s",
    )

    try:
        inputs, output = split_paths(args.paths)
        check_output(output, args.force, args.dry_run)
    except ValueError as exc:
        parser.error(str(exc))

    result = load(inputs, output=output, recursive=options.recursive)
    report_load(result, options.verbose)

    if not result.pages:
        print("nothing to do: no readable pages were found", file=sys.stderr)
        return EXIT_FAILED

    print(
        f"loaded {len(result.pages)} pages from {result.document_count} documents",
        file=sys.stderr,
    )
    print(
        "eco-print: detection, packing and output are not built yet "
        "(M3-M5); nothing was written.",
        file=sys.stderr,
    )
    return EXIT_OK if result.ok else EXIT_PARTIAL


if __name__ == "__main__":
    raise SystemExit(main())

"""The command-line front end (UC-01, UC-02).

The option flags are not written out here: `settings.add_options` generates them
from `Options`, which is what keeps the CLI and the GUI in step (UC-08). Only the
arguments that concern the run rather than the output are declared locally.

The work itself lives in `pipeline.run`, which the GUI drives too.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .pipeline import RunResult, run
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
        "--gui", action="store_true",
        help="open the graphical interface, pre-loaded with any inputs given",
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


def report(result: RunResult, options: Options) -> None:
    """Tell the user what was skipped, and — when asked — what was decided."""
    for error in result.errors:
        print(f"skipped {error.path}: {error.reason}", file=sys.stderr)

    if options.verbose:
        for detection in result.detections:
            print(f"  {detection.describe()}")
    elif result.blank_pages:
        count = len(result.blank_pages)
        page_word = "page" if count == 1 else "pages"
        print(f"skipped {count} blank {page_word}", file=sys.stderr)

    if result.packing:
        for block in result.packing.oversized:
            print(
                f"warning: {block.page.label} is taller than one sheet "
                f"({block.height:.0f}pt); it was placed alone and is clipped",
                file=sys.stderr,
            )


def start_gui(paths: list[str]) -> int:
    """Open the window, or explain why it cannot be opened."""
    from .gui import MissingGui, launch

    try:
        return launch(paths)
    except MissingGui as exc:
        print(f"eco-print: {exc}", file=sys.stderr)
        return EXIT_FAILED


def _attach_windows_console() -> None:
    """Join the launching terminal's console on a windowed Windows build.

    A packaged --windowed build has no console of its own, so printed output
    silently vanishes even when the user ran the exe from cmd.exe or
    PowerShell -- CLI mode would otherwise look broken despite working
    correctly underneath. AttachConsole(-1) attaches to the parent process's
    console when one launched this process, and is a harmless no-op (it
    simply fails) both when launched by double-click, where there is no
    console to join, and in an ordinary console build, which already owns
    one. See UC-09.
    """
    if sys.platform != "win32":
        return
    import ctypes

    attach_parent_process = -1
    if not ctypes.windll.kernel32.AttachConsole(attach_parent_process):
        return
    sys.stdout = open("CONOUT$", "w")
    sys.stderr = open("CONOUT$", "w")
    sys.stdin = open("CONIN$", "r")


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns the process exit code."""
    _attach_windows_console()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gui or not args.paths:
        # No arguments at all means the GUI; --gui pre-loads it (UC-03).
        return start_gui([str(path) for path in args.paths])

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

    result = run(inputs, output, options, write_output=not args.dry_run)
    report(result, options)

    if not result.blocks:
        # A zero-page document is worse than no document at all (UC-07).
        print("nothing to do: no printable content was found", file=sys.stderr)
        return EXIT_FAILED

    print(result.summary())
    if args.dry_run:
        print(f"dry run: {output} was not written")
    else:
        print(f"wrote {output}")

    return EXIT_OK if result.ok else EXIT_PARTIAL


if __name__ == "__main__":
    raise SystemExit(main())

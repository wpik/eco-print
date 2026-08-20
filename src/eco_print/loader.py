"""Turning what the user pointed at into a list of pages (UC-02, UC-07).

Two steps, kept separate because they fail differently: `expand_inputs` resolves
paths and never touches file contents, while `load_pages` opens documents and is
where damaged and encrypted files are dealt with.
"""
from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .model import LoadResult, SourceError, SourcePage

log = logging.getLogger(__name__)

PDF_SUFFIX = ".pdf"


def expand_inputs(
    inputs: list[Path], output: Path | None = None, recursive: bool = False
) -> list[Path]:
    """Resolve files and directories into an ordered list of PDF paths.

    Order is the user's: each argument's expansion is spliced in at that
    argument's position, so a mix of files and directories stays left-to-right.
    Within a directory, files are sorted case-insensitively by name — filesystem
    order is not reproducible and the output would otherwise vary between runs.

    `output` is excluded wherever it appears. Without that, re-running a command
    whose output lands in a scanned directory would feed the previous result
    back in.
    """
    resolved_output = output.resolve() if output else None
    paths: list[Path] = []

    for item in inputs:
        if item.is_dir():
            found = item.rglob("*") if recursive else item.glob("*")
            paths.extend(sorted(
                (p for p in found if _is_pdf(p)),
                key=lambda p: (str(p.parent).lower(), p.name.lower()),
            ))
        else:
            # A named file is taken at face value: if the user typed it, they
            # mean it, and a wrong suffix is reported by the loader rather than
            # silently ignored here.
            paths.append(item)

    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in paths:
        full = path.resolve()
        if resolved_output and full == resolved_output:
            log.debug("skipping %s: it is the output file", path)
            continue
        if full in seen and path.is_dir():
            continue
        seen.add(full)
        ordered.append(path)
    return ordered


def _is_pdf(path: Path) -> bool:
    """A regular, non-hidden file with a .pdf suffix."""
    return (
        path.is_file()
        and path.suffix.lower() == PDF_SUFFIX
        and not path.name.startswith(".")
    )


def load_pages(paths: list[Path]) -> LoadResult:
    """Open each document and describe its pages.

    Every source is handled independently: a failure is recorded against that
    source and the rest of the batch continues (UC-07).
    """
    pages: list[SourcePage] = []
    errors: list[SourceError] = []

    for path in paths:
        try:
            pages.extend(_pages_of(path))
        except SourceUnusable as exc:
            log.warning("skipping %s: %s", path, exc)
            errors.append(SourceError(path, str(exc)))

    return LoadResult(pages=pages, errors=errors)


class SourceUnusable(Exception):
    """One input cannot be used. Carries the sentence shown to the user."""


def _pages_of(path: Path) -> list[SourcePage]:
    """Describe one document's pages, or explain why it cannot be read."""
    if not path.exists():
        raise SourceUnusable("no such file")
    if path.is_dir():
        raise SourceUnusable("is a directory")

    try:
        reader = PdfReader(str(path))
    except PdfReadError as exc:
        raise SourceUnusable(f"not a readable PDF ({exc})") from exc
    except OSError as exc:
        raise SourceUnusable(f"cannot be opened ({exc.strerror or exc})") from exc
    except Exception as exc:  # pypdf raises assorted types on damaged files
        raise SourceUnusable(f"not a readable PDF ({type(exc).__name__})") from exc

    password = _decrypt(reader, path)

    try:
        count = len(reader.pages)
    except Exception as exc:
        raise SourceUnusable(f"page tree is damaged ({type(exc).__name__})") from exc
    if count == 0:
        raise SourceUnusable("contains no pages")

    pages: list[SourcePage] = []
    for index in range(count):
        try:
            box = reader.pages[index].mediabox
            width, height = float(box.width), float(box.height)
        except Exception as exc:
            raise SourceUnusable(
                f"page {index + 1} is damaged ({type(exc).__name__})"
            ) from exc
        pages.append(SourcePage(path, index, width, height, password))
    return pages


def _decrypt(reader: PdfReader, path: Path) -> str | None:
    """Open an encrypted document, if an empty user password suffices (UC-07).

    Owner-password restrictions on printing or copying are not a reason to
    refuse: the user already possesses the document.
    """
    if not reader.is_encrypted:
        return None
    try:
        if reader.decrypt(""):
            log.debug("%s: decrypted with an empty user password", path)
            return ""
    except NotImplementedError as exc:
        raise SourceUnusable(f"uses unsupported encryption ({exc})") from exc
    except Exception as exc:
        raise SourceUnusable(f"cannot be decrypted ({type(exc).__name__})") from exc
    raise SourceUnusable("is password-protected")


def load(
    inputs: list[Path], output: Path | None = None, recursive: bool = False
) -> LoadResult:
    """Expand the inputs and load every page they name."""
    return load_pages(expand_inputs(inputs, output, recursive))

"""Shared fixtures: paths into the generated corpus (see data/generate_fixtures.py)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"

#: The five ordinary documents that must pack onto two sheets.
STATEMENTS = [DATA / f"statement-{name}.pdf" for name in "abcde"]


@pytest.fixture
def data_dir() -> Path:
    return DATA


@pytest.fixture
def statement_dir(tmp_path: Path) -> Path:
    """A directory holding only the five statements, safe to write into."""
    target = tmp_path / "statements"
    target.mkdir()
    for source in STATEMENTS:
        shutil.copy(source, target / source.name)
    return target


@pytest.fixture
def make_block():
    """Build a block of a given height without touching the filesystem.

    Packing cares only about heights, so most packer tests need no PDFs at all.
    """
    from eco_print.model import Block, ContentBox, SourcePage

    def build(height: float, name: str = "b", width: float = 595.275) -> Block:
        page = SourcePage(Path(f"/nowhere/{name}.pdf"), 0, width, 841.889)
        return Block(page, ContentBox(0.0, 0.0, width, height))

    return build


@pytest.fixture
def blocks_from():
    """Detect real blocks from named fixtures, in order."""
    from eco_print.detect import detect_all
    from eco_print.loader import load_pages
    from eco_print.model import Block

    def build(stems: list[str], options=None) -> list[Block]:
        paths = [DATA / f"{stem}.pdf" for stem in stems]
        pages = load_pages(paths).pages
        return [Block(d.page, d.box) for d in detect_all(pages, options).boxed]

    return build

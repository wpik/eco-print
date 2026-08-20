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

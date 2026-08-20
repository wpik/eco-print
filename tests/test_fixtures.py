"""The fixture corpus must match its generator, and its description.

If a fixture is edited by hand, or the generator changes without the committed
files being refreshed, the corpus stops meaning what docs/README.md says it
means — and every test asserting a detected height becomes a test of nothing.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"
GENERATOR = DATA / "generate_fixtures.py"

#: Regenerating these must reproduce the committed bytes exactly. `encrypted.pdf`
#: is excluded: its bytes are pypdf's business, not the generator's.
DETERMINISTIC = sorted(p.name for p in DATA.glob("*.pdf") if p.name != "encrypted.pdf")


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_fixtures", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_generator_is_committed_with_its_output():
    assert GENERATOR.is_file()
    assert DETERMINISTIC, "no fixtures found"


@pytest.mark.parametrize("name", DETERMINISTIC)
def test_regeneration_reproduces_the_committed_fixture(name, tmp_path: Path):
    load_generator().build(tmp_path)
    assert (tmp_path / name).read_bytes() == (DATA / name).read_bytes(), (
        f"{name} differs from what the generator produces; "
        f"re-run tests/data/generate_fixtures.py and commit the result"
    )


def test_the_corpus_covers_every_documented_case():
    """The fixture names docs/README.md promises are the ones that exist."""
    expected = {
        "statement-a", "statement-b", "statement-c", "statement-d", "statement-e",
        "packing-a", "packing-b", "packing-c",
        "with-footer", "two-blocks", "full-page", "blank", "landscape",
        "multipage", "oversized", "encrypted",
    }
    assert {p.stem for p in DATA.glob("*.pdf")} == expected

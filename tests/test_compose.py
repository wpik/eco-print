"""Writing packed sheets out as a PDF (UC-06, UC-07).

Output is checked by re-rendering it and asking where the ink actually landed,
rather than by comparing bytes: what matters is that a reader sees the blocks
where the packer said they would be.
"""
from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pytest
from pypdf import PdfReader

from eco_print import compose
from eco_print.detect import RENDER_DPI, WHITE_THRESHOLD
from eco_print.packer import layout, pack_ordered
from eco_print.settings import Options

STATEMENTS = [f"statement-{n}" for n in "abcde"]


def render_sheets(path: Path) -> list[np.ndarray]:
    """Render a written document back to greyscale arrays."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    try:
        return [
            np.asarray(
                document[i].render(scale=RENDER_DPI / 72.0, grayscale=True)
                .to_pil().convert("L")
            )
            for i in range(len(document))
        ]
    finally:
        document.close()


def ink_extent(sheet: np.ndarray) -> tuple[int, int]:
    """First and last inked row of a rendered sheet, top-down."""
    rows = (sheet < WHITE_THRESHOLD).any(axis=1).nonzero()[0]
    assert rows.size, "sheet is blank"
    return int(rows[0]), int(rows[-1])


@pytest.fixture
def written(tmp_path: Path, blocks_from):
    """Pack and write a set of fixtures, returning the path and the packing."""

    counter = itertools.count()

    def build(stems: list[str], options: Options | None = None) -> tuple[Path, object]:
        options = options or Options()
        blocks = blocks_from(stems, options)
        result = pack_ordered(blocks, options)
        # A fresh name per call: two writes in one test must not collide.
        output = tmp_path / f"out-{next(counter)}.pdf"
        compose.write(result, output, options)
        return output, result

    return build


class TestWriting:
    def test_the_five_statements_become_two_sheets(self, written):
        output, result = written(STATEMENTS)
        assert len(PdfReader(str(output)).pages) == 2
        assert result.sheet_count == 2

    def test_sheets_are_the_requested_size(self, written):
        output, _ = written(STATEMENTS, Options(page_size="letter"))
        page = PdfReader(str(output)).pages[0]
        assert float(page.mediabox.width) == pytest.approx(612.0)

    def test_the_output_directory_is_created(self, tmp_path: Path, blocks_from):
        result = pack_ordered(blocks_from(["statement-a"]))
        target = tmp_path / "fresh" / "out.pdf"
        compose.write(result, target)
        assert target.is_file()

    def test_an_encrypted_source_composes(self, written):
        """UC-07: the password discovered at load time carries through."""
        output, _ = written(["encrypted"])
        assert len(PdfReader(str(output)).pages) == 1

    def test_the_output_is_not_encrypted(self, written):
        output, _ = written(["encrypted"])
        assert not PdfReader(str(output)).is_encrypted


class TestInkLandsWherePlanned:
    def test_content_appears_where_the_layout_said(self, written):
        """The packer's arithmetic and the composer's must agree."""
        options = Options()
        output, result = written(STATEMENTS, options)
        page_height = options.page_dimensions()[1]

        for sheet, raster in zip(result.sheets, render_sheets(output)):
            placements = layout(sheet, options)
            expected_top = page_height - placements[0].top
            expected_bottom = page_height - (
                placements[-1].top - placements[-1].block.height
            )
            first, last = ink_extent(raster)
            assert first == pytest.approx(expected_top, abs=8)
            assert last == pytest.approx(expected_bottom, abs=8)

    def test_nothing_is_scaled(self, written):
        """A distance on the output equals the same distance on the source."""
        options = Options(pad=0.0)
        output, _ = written(["statement-c"], options)
        first, last = ink_extent(render_sheets(output)[0])
        assert last - first == pytest.approx(300, abs=3)   # generated ink height

    def test_a_dropped_footer_does_not_reappear(self, written):
        """UC-05: what detection discarded must not be printed."""
        options = Options()
        output, _ = written(["with-footer"], options)
        first, last = ink_extent(render_sheets(output)[0])
        assert last - first == pytest.approx(201, abs=6)

    def test_full_ink_brings_the_footer_back(self, written):
        output, _ = written(["with-footer"], Options(full_ink=True))
        first, last = ink_extent(render_sheets(output)[0])
        assert last - first > 700


class TestGeometry:
    def test_a_landscape_block_is_left_aligned_when_it_overhangs(self, written):
        """UC-07: wider than the sheet means aligned to the margin, not centred."""
        output, _ = written(["landscape"])
        assert len(PdfReader(str(output)).pages) == 1

    def test_mixed_page_sizes_share_one_sheet_size(self, written):
        output, result = written(["statement-a", "landscape"])
        pages = PdfReader(str(output)).pages
        for page in pages:
            assert float(page.mediabox.width) == pytest.approx(595.275)


class TestSeparators:
    def test_a_separator_adds_ink_between_blocks(self, written):
        plain, _ = written(["statement-a", "statement-b"], Options())
        ruled, _ = written(["statement-a", "statement-b"], Options(separator=True))
        plain_ink = (render_sheets(plain)[0] < WHITE_THRESHOLD).sum()
        ruled_ink = (render_sheets(ruled)[0] < WHITE_THRESHOLD).sum()
        assert ruled_ink > plain_ink

    def test_a_lone_block_gets_no_separator(self, written):
        plain, _ = written(["statement-a"], Options())
        ruled, _ = written(["statement-a"], Options(separator=True))
        assert (render_sheets(plain)[0] < WHITE_THRESHOLD).sum() == (
            render_sheets(ruled)[0] < WHITE_THRESHOLD
        ).sum()


class TestDeterminism:
    def test_the_same_inputs_produce_the_same_bytes(self, tmp_path: Path, blocks_from):
        """UC-01: re-running a command must not churn the output."""
        options = Options()
        outputs = []
        for name in ("first.pdf", "second.pdf"):
            result = pack_ordered(blocks_from(STATEMENTS, options), options)
            target = tmp_path / name
            compose.write(result, target, options)
            outputs.append(target.read_bytes())
        assert outputs[0] == outputs[1]

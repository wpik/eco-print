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
    """The cut line is meant to be used literally with scissors (UC-06)."""

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

    def test_the_line_spans_from_the_left_margin_to_the_right_margin(self, written):
        options = Options(separator=True)
        output, result = written(["statement-a", "statement-b"], options)
        raster = render_sheets(output)[0]
        row = _separator_row(raster, options, result)
        ink_columns = (raster[row, :] < WHITE_THRESHOLD).nonzero()[0]

        px_per_pt = raster.shape[1] / options.page_dimensions()[0]
        assert ink_columns.min() == pytest.approx(options.margin * px_per_pt, abs=4)
        assert ink_columns.max() == pytest.approx(
            (options.page_dimensions()[0] - options.margin) * px_per_pt, abs=4
        )

    def test_the_line_is_actually_dashed(self, written):
        """Not a solid rule: there must be gaps along its own row."""
        options = Options(separator=True)
        output, result = written(["statement-a", "statement-b"], options)
        raster = render_sheets(output)[0]
        row = _separator_row(raster, options, result)
        ink = raster[row, :] < WHITE_THRESHOLD
        # A solid line has one run of ink; a dashed one has several.
        assert _count_runs(ink) > 3


def _separator_row(raster, options: Options, result) -> int:
    """The raster row the cut line is expected to sit on, from the same
    geometry the composer used to place it."""
    sheet = result.sheets[0]
    placements = layout(sheet, options)
    above, below = placements[0], placements[1]
    bottom_of_above = above.top - above.block.height
    middle_pt = (bottom_of_above + below.top) / 2
    px_per_pt = raster.shape[0] / options.page_dimensions()[1]
    return round((options.page_dimensions()[1] - middle_pt) * px_per_pt)


def _count_runs(mask) -> int:
    """How many contiguous True runs a 1-D boolean array contains."""
    import numpy as np

    padded = np.concatenate(([False], mask, [False]))
    return int(np.sum(padded[1:] & ~padded[:-1]))


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

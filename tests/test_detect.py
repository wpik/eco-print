"""Automatic content detection (UC-05).

The numbers asserted here are the ones the fixture generator chose: each fixture
pins its ink extent with hairline rules, so a detected height is
`ink height + 2 * pad` and nothing is left to a text renderer's discretion.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from eco_print.detect import (
    BAND_MERGE_PT,
    Detection,
    bands,
    clear_cache,
    detect,
    detect_all,
    ink_rows,
    render_gray,
)
from eco_print.loader import load_pages
from eco_print.settings import Options

#: fixture stem -> ink height in points, as generated
INK_HEIGHTS = {
    "statement-a": 151, "statement-b": 231, "statement-c": 301,
    "statement-d": 181, "statement-e": 261,
    "packing-a": 391, "packing-b": 501, "packing-c": 341,
    "landscape": 181,
}


def page_of(data_dir: Path, stem: str, index: int = 0):
    return load_pages([data_dir / f"{stem}.pdf"]).pages[index]


def detect_stem(data_dir: Path, stem: str, options: Options | None = None) -> Detection:
    return detect(page_of(data_dir, stem), options)


class TestRendering:
    def test_a_page_renders_about_one_pixel_per_point(self, data_dir: Path):
        """The rasteriser rounds up to whole pixels, so detect() derives its
        scale from the raster rather than assuming an exact 1:1."""
        page = page_of(data_dir, "statement-a")
        height, width = render_gray(page).shape
        assert height == pytest.approx(page.height, abs=1)
        assert width == pytest.approx(page.width, abs=1)

    def test_landscape_renders_landscape(self, data_dir: Path):
        height, width = render_gray(page_of(data_dir, "landscape")).shape
        assert width > height

    def test_an_encrypted_page_renders(self, data_dir: Path):
        """UC-07: the password found at load time is carried through."""
        assert render_gray(page_of(data_dir, "encrypted")).size > 0

    def test_rendering_is_cached(self, data_dir: Path):
        clear_cache()
        page = page_of(data_dir, "statement-a")
        assert render_gray(page) is render_gray(page)


class TestInkRows:
    def test_a_blank_page_has_no_ink(self, data_dir: Path):
        assert not ink_rows(render_gray(page_of(data_dir, "blank"))).any()

    def test_ink_is_found_where_the_generator_put_it(self, data_dir: Path):
        rows = ink_rows(render_gray(page_of(data_dir, "statement-a")))
        found = rows.nonzero()[0]
        assert found[0] == pytest.approx(40, abs=2)
        assert found[-1] == pytest.approx(190, abs=2)

    def test_a_border_hugging_the_page_edge_is_ignored(self, data_dir: Path):
        """A scan border must not anchor the box to the paper's edge."""
        gray = render_gray(page_of(data_dir, "statement-a")).copy()
        gray[0:2, :] = 0          # full-width rule along the very top
        gray[-2:, :] = 0          # ...and the very bottom
        found = ink_rows(gray).nonzero()[0]
        assert found[0] > 30

    def test_a_border_down_the_side_is_ignored(self, data_dir: Path):
        gray = render_gray(page_of(data_dir, "statement-a")).copy()
        gray[:, 0:2] = 0
        found = ink_rows(gray).nonzero()[0]
        assert found[-1] < 200


class TestBands:
    def test_adjacent_rows_form_one_band(self):
        import numpy as np

        rows = np.zeros(100, dtype=bool)
        rows[10:20] = True
        assert bands(rows, BAND_MERGE_PT) == [(10, 19)]

    def test_line_spacing_is_merged_away(self):
        import numpy as np

        rows = np.zeros(100, dtype=bool)
        rows[10:12] = True
        rows[18:20] = True          # 6 rows apart: ordinary leading
        assert bands(rows, BAND_MERGE_PT) == [(10, 19)]

    def test_a_wide_separation_keeps_bands_apart(self):
        import numpy as np

        rows = np.zeros(100, dtype=bool)
        rows[10:12] = True
        rows[60:62] = True
        assert bands(rows, BAND_MERGE_PT) == [(10, 11), (60, 61)]


class TestDetectedHeights:
    @pytest.mark.parametrize("stem,ink", sorted(INK_HEIGHTS.items()))
    def test_height_is_the_ink_plus_padding(self, data_dir: Path, stem: str, ink: int):
        detection = detect_stem(data_dir, stem)
        assert detection.box is not None
        assert detection.box.height == pytest.approx(ink + 2 * Options().pad, abs=2)

    def test_padding_widens_the_box(self, data_dir: Path):
        tight = detect_stem(data_dir, "statement-a", Options(pad=0.0))
        padded = detect_stem(data_dir, "statement-a", Options(pad=20.0))
        assert padded.box.height == pytest.approx(tight.box.height + 40, abs=1)

    def test_a_block_spans_the_full_page_width(self, data_dir: Path):
        """UC-04: cropping is vertical only; a narrower block saves no paper."""
        page = page_of(data_dir, "statement-a")
        box = detect(page).box
        assert (box.left, box.right) == (0.0, page.width)

    def test_the_box_never_leaves_the_page(self, data_dir: Path):
        """Padding must not push the box off an already full sheet."""
        page = page_of(data_dir, "oversized")
        box = detect(page, Options(pad=40.0)).box
        assert box.bottom >= 0.0
        assert box.top <= page.height


class TestLargestGapRule:
    """The two fixtures that probe the rule differ in what it must decide."""

    def test_a_trailing_footer_is_dropped(self, data_dir: Path):
        detection = detect_stem(data_dir, "with-footer")
        assert detection.method == "gap-cut"
        assert detection.box.height == pytest.approx(201 + 12, abs=3)
        assert detection.dropped > 400

    def test_a_second_real_block_is_kept(self, data_dir: Path):
        """The safety condition: what falls below is a section, not a footnote."""
        detection = detect_stem(data_dir, "two-blocks")
        assert detection.method == "ink-box"
        assert detection.box.height > 700
        assert detection.dropped == 0

    def test_solid_text_has_no_structural_gap(self, data_dir: Path):
        detection = detect_stem(data_dir, "full-page")
        assert detection.method == "ink-box"
        assert detection.box.height == pytest.approx(761 + 12, abs=3)

    def test_full_ink_keeps_the_footer(self, data_dir: Path):
        """UC-05: --full-ink switches the rule off entirely."""
        detection = detect_stem(data_dir, "with-footer", Options(full_ink=True))
        assert detection.method == "full-ink"
        assert detection.box.height > 700
        assert detection.box.origin == "full-ink"

    def test_full_ink_never_drops_anything(self, data_dir: Path):
        for stem in ("with-footer", "two-blocks", "statement-a"):
            assert detect_stem(data_dir, stem, Options(full_ink=True)).dropped == 0


class TestBlankPages:
    def test_a_blank_page_yields_no_block(self, data_dir: Path):
        detection = detect_stem(data_dir, "blank")
        assert detection.is_blank
        assert detection.method == "blank"

    def test_a_blank_page_is_not_an_error(self, data_dir: Path):
        result = detect_all(load_pages([data_dir / "blank.pdf"]).pages)
        assert result.ok
        assert result.boxed == []
        assert len(result.blank) == 1


class TestBatch:
    def test_every_page_of_a_document_is_detected_independently(self, data_dir: Path):
        pages = load_pages([data_dir / "multipage.pdf"]).pages
        heights = [d.box.height for d in detect_all(pages).boxed]
        assert heights == pytest.approx([121 + 12, 301 + 12, 201 + 12], abs=2)

    def test_the_five_statements_all_yield_blocks(self, statement_dir: Path):
        from eco_print.loader import load

        result = detect_all(load([statement_dir]).pages)
        assert len(result.boxed) == 5
        assert result.ok

    def test_an_unreadable_page_is_isolated(self, data_dir: Path, tmp_path: Path):
        """UC-07: a rendering failure loses one page, not the batch."""
        from eco_print.model import SourcePage

        good = page_of(data_dir, "statement-a")
        missing = SourcePage(tmp_path / "gone.pdf", 0, 595.0, 842.0)
        result = detect_all([good, missing])
        assert len(result.boxed) == 1
        assert len(result.errors) == 1
        assert not result.ok


class TestReporting:
    def test_a_cut_is_explained(self, data_dir: Path):
        line = detect_stem(data_dir, "with-footer").describe()
        assert "dropped" in line and "gap-cut" in line

    def test_a_blank_page_is_explained(self, data_dir: Path):
        assert "blank" in detect_stem(data_dir, "blank").describe()

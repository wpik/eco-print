"""Packing blocks onto sheets, ordered mode (UC-06)."""
from __future__ import annotations

import pytest

from eco_print.packer import Sheet, layout, lower_bound, pack, pack_ordered
from eco_print.settings import Options

USABLE = Options().usable_height()   # 785.889 pt on A4 with a 28pt margin


class TestOrderedPacking:
    def test_the_five_statements_fill_two_sheets_three_then_two(self, blocks_from):
        """The headline requirement: five documents onto two sheets."""
        blocks = blocks_from([f"statement-{n}" for n in "abcde"])
        result = pack_ordered(blocks)
        assert [len(sheet.blocks) for sheet in result.sheets] == [3, 2]
        assert result.sheets_saved == 3

    def test_order_is_preserved_exactly(self, blocks_from):
        blocks = blocks_from([f"statement-{n}" for n in "abcde"])
        result = pack_ordered(blocks)
        packed = [b for sheet in result.sheets for b in sheet.blocks]
        assert packed == blocks

    def test_every_block_is_placed_exactly_once(self, blocks_from):
        blocks = blocks_from([f"statement-{n}" for n in "abcde"])
        result = pack_ordered(blocks)
        assert result.block_count == len(blocks)

    def test_no_sheet_exceeds_the_usable_height(self, make_block):
        blocks = [make_block(h) for h in (200, 300, 250, 180, 400, 120)]
        result = pack_ordered(blocks)
        for sheet in result.sheets:
            assert sheet.height_with_gaps(Options().gap) <= USABLE + 1e-9

    def test_a_single_block_needs_one_sheet(self, make_block):
        assert pack_ordered([make_block(100)]).sheet_count == 1

    def test_nothing_to_pack_yields_no_sheets(self):
        assert pack_ordered([]).sheet_count == 0

    def test_blocks_over_half_the_height_never_share(self, make_block):
        """N blocks that cannot pair must produce exactly N sheets."""
        blocks = [make_block(USABLE * 0.6) for _ in range(4)]
        assert pack_ordered(blocks).sheet_count == 4

    def test_the_gap_is_counted_when_deciding_to_break(self, make_block):
        """Two blocks that sum to the usable height still need a gap between."""
        blocks = [make_block(USABLE / 2), make_block(USABLE / 2)]
        assert pack_ordered(blocks).sheet_count == 2

    def test_a_smaller_gap_can_save_a_sheet(self, make_block):
        blocks = [make_block(USABLE / 2), make_block(USABLE / 2)]
        assert pack_ordered(blocks, Options(gap=0.0)).sheet_count == 1


class TestOversizedBlocks:
    def test_a_block_taller_than_a_sheet_gets_one_to_itself(self, make_block):
        result = pack_ordered([make_block(USABLE + 50)])
        assert result.sheet_count == 1
        assert len(result.oversized) == 1

    def test_an_oversized_block_does_not_absorb_its_neighbours(self, make_block):
        blocks = [make_block(100, "a"), make_block(USABLE + 50, "big"), make_block(100, "c")]
        result = pack_ordered(blocks)
        assert [len(s.blocks) for s in result.sheets] == [1, 1, 1]
        assert result.block_count == 3

    def test_the_real_oversized_fixture_is_reported(self, blocks_from):
        result = pack_ordered(blocks_from(["oversized"]))
        assert len(result.oversized) == 1


class TestLowerBound:
    def test_blocks_that_fit_one_sheet_bound_at_one(self, make_block):
        assert lower_bound([make_block(100), make_block(100)], Options()) == 1

    def test_the_bound_is_never_beaten_by_a_real_packing(self, make_block):
        for heights in ([200, 300, 250], [400, 500, 350], [100] * 12, [780, 10]):
            blocks = [make_block(h) for h in heights]
            assert pack_ordered(blocks).sheet_count >= lower_bound(blocks, Options())

    def test_oversized_blocks_each_force_their_own_sheet(self, make_block):
        blocks = [make_block(USABLE + 10), make_block(USABLE + 10), make_block(10)]
        assert lower_bound(blocks, Options()) == 3


class TestLayout:
    def test_blocks_run_down_the_sheet_in_order(self, make_block):
        sheet = Sheet([make_block(100, "a"), make_block(100, "b")])
        placements = layout(sheet, Options())
        assert placements[0].top > placements[1].top

    def test_blocks_never_overlap(self, make_block):
        sheet = Sheet([make_block(200, "a"), make_block(150, "b"), make_block(120, "c")])
        placements = layout(sheet, Options())
        for above, below in zip(placements, placements[1:]):
            assert above.top - above.block.height >= below.top

    def test_nothing_crosses_a_margin(self, make_block):
        options = Options()
        page_height = options.page_dimensions()[1]
        sheet = Sheet([make_block(200, "a"), make_block(150, "b")])
        placements = layout(sheet, options)
        assert placements[0].top <= page_height - options.margin + 1e-9
        last = placements[-1]
        assert last.top - last.block.height >= options.margin - 1e-9

    def test_leftover_space_is_spread_evenly(self, make_block):
        """A half-full sheet reads as layout, not as a truncation (UC-06)."""
        options = Options()
        page_height = options.page_dimensions()[1]
        sheet = Sheet([make_block(100, "a"), make_block(100, "b")])
        placements = layout(sheet, options)
        top_space = page_height - options.margin - placements[0].top
        between = placements[0].top - 100 - placements[1].top
        bottom_space = placements[1].top - 100 - options.margin
        assert top_space == pytest.approx(between, abs=0.01)
        assert between == pytest.approx(bottom_space, abs=0.01)

    def test_a_gap_is_never_narrower_than_the_minimum(self, make_block):
        options = Options(gap=40.0)
        heights = [240.0, 240.0, 240.0]
        sheet = Sheet([make_block(h, str(i)) for i, h in enumerate(heights)])
        placements = layout(sheet, options)
        for above, below in zip(placements, placements[1:]):
            assert above.top - above.block.height - below.top >= options.gap - 1e-9

    def test_an_empty_sheet_places_nothing(self):
        assert layout(Sheet(), Options()) == []


class TestModeSelection:
    def test_pack_uses_the_ordered_packer_by_default(self, blocks_from):
        result = pack(blocks_from([f"statement-{n}" for n in "abcde"]))
        assert result.reordered is False
        assert result.sheet_count == 2

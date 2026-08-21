"""Packing with input order given up (UC-06, --reorder)."""
from __future__ import annotations

import random

import pytest

from eco_print import repack
from eco_print.packer import lower_bound, pack, pack_ordered
from eco_print.repack import pack_reordered
from eco_print.settings import Options

USABLE = Options().usable_height()
PACKING_FIXTURES = [f"packing-{n}" for n in "abc"]


class TestTheHeadlineCase:
    def test_ordered_needs_three_sheets(self, blocks_from):
        assert pack_ordered(blocks_from(PACKING_FIXTURES)).sheet_count == 3

    def test_reordering_needs_only_two(self, blocks_from):
        result = pack_reordered(blocks_from(PACKING_FIXTURES))
        assert result.sheet_count == 2

    def test_the_saving_is_reported(self, blocks_from):
        """UC-06: the user is told what the flag actually bought."""
        result = pack_reordered(blocks_from(PACKING_FIXTURES))
        assert result.alternative_sheets == 3
        assert result.reorder_saved == 1

    def test_no_saving_is_reported_as_none(self, blocks_from):
        """Reordering the statements cannot beat 2 sheets, and says so."""
        result = pack_reordered(blocks_from([f"statement-{n}" for n in "abcde"]))
        assert result.sheet_count == 2
        assert result.reorder_saved == 0

    def test_the_result_is_provably_optimal_here(self, blocks_from):
        blocks = blocks_from(PACKING_FIXTURES)
        assert pack_reordered(blocks).sheet_count == lower_bound(blocks, Options())


class TestInvariants:
    """The failures that must never escape, asserted on every packing."""

    def test_every_block_appears_exactly_once(self, make_block):
        blocks = [make_block(h, str(i)) for i, h in enumerate([300, 200, 500, 150, 250])]
        result = pack_reordered(blocks)
        packed = [b for sheet in result.sheets for b in sheet.blocks]
        assert sorted(id(b) for b in packed) == sorted(id(b) for b in blocks)

    def test_no_sheet_exceeds_the_usable_height(self, make_block):
        blocks = [make_block(h, str(i)) for i, h in enumerate([300, 200, 500, 150, 250])]
        for sheet in pack_reordered(blocks).sheets:
            assert sheet.height_with_gaps(Options().gap) <= USABLE + 1e-9

    def test_nothing_to_pack_yields_no_sheets(self):
        assert pack_reordered([]).sheet_count == 0

    @pytest.mark.parametrize("seed", range(25))
    def test_random_batches_hold_every_invariant(self, make_block, seed):
        """A sweep: reordering is never worse than ordering, never beats the bound."""
        rng = random.Random(seed)
        options = Options()
        heights = [rng.uniform(40, USABLE) for _ in range(rng.randint(1, 14))]
        blocks = [make_block(h, str(i)) for i, h in enumerate(heights)]

        ordered = pack_ordered(blocks, options)
        reordered = pack_reordered(blocks, options)

        assert reordered.block_count == len(blocks)
        assert reordered.sheet_count <= ordered.sheet_count
        assert reordered.sheet_count >= lower_bound(blocks, options)
        for sheet in reordered.sheets:
            assert sheet.height_with_gaps(options.gap) <= USABLE + 1e-9


class TestOversized:
    def test_an_oversized_block_still_gets_its_own_sheet(self, make_block):
        blocks = [make_block(100, "a"), make_block(USABLE + 60, "big"), make_block(100, "c")]
        result = pack_reordered(blocks)
        assert len(result.oversized) == 1
        assert result.block_count == 3
        assert result.sheet_count == 2      # the two small ones share

    def test_only_oversized_blocks_means_one_sheet_each(self, make_block):
        blocks = [make_block(USABLE + 10, str(i)) for i in range(3)]
        assert pack_reordered(blocks).sheet_count == 3


class TestWithinASheet:
    def test_blocks_are_emitted_tallest_first(self, make_block):
        """Ragged whitespace belongs at the bottom of the sheet, not between."""
        blocks = [make_block(100, "small"), make_block(300, "tall"), make_block(200, "mid")]
        sheet = pack_reordered(blocks).sheets[0]
        heights = [b.height for b in sheet.blocks]
        assert heights == sorted(heights, reverse=True)


class TestSearchTiers:
    def test_the_exact_search_is_skipped_for_large_batches(self, make_block, monkeypatch):
        """FFD's guarantee is the sensible answer once a batch is big."""
        monkeypatch.setattr(repack, "EXACT_SEARCH_LIMIT", 3)
        blocks = [make_block(200, str(i)) for i in range(10)]
        result = pack_reordered(blocks)
        assert result.block_count == 10

    def test_an_expired_budget_still_returns_the_ffd_result(
        self, make_block, monkeypatch
    ):
        monkeypatch.setattr(repack, "EXACT_SEARCH_BUDGET", 0.0)
        blocks = [make_block(h, str(i)) for i, h in enumerate([390, 500, 340])]
        result = pack_reordered(blocks)
        assert result.block_count == 3
        assert result.sheet_count <= pack_ordered(blocks).sheet_count

    def test_the_search_finds_a_packing_ffd_misses(self, make_block, monkeypatch):
        """Constructed so first-fit-decreasing leaves one sheet too many."""
        monkeypatch.setattr(repack, "_first_fit_decreasing", lambda blocks, options: [
            __import__("eco_print.packer", fromlist=["Sheet"]).Sheet([b]) for b in blocks
        ])
        blocks = [make_block(h, str(i)) for i, h in enumerate([300, 300, 100])]
        result = pack_reordered(blocks)
        assert result.sheet_count == 1      # 300+300+100 plus gaps fits one sheet


class TestDispatch:
    def test_the_flag_selects_the_reordering_packer(self, blocks_from):
        result = pack(blocks_from(PACKING_FIXTURES), Options(reorder=True))
        assert result.reordered is True
        assert result.sheet_count == 2

    def test_without_the_flag_order_is_kept(self, blocks_from):
        result = pack(blocks_from(PACKING_FIXTURES), Options(reorder=False))
        assert result.reordered is False
        assert result.sheet_count == 3

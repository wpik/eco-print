"""The GUI's model (UC-03, UC-04, UC-08).

No Qt here: the document list, crops, live estimate and command-line transfer
are plain Python, so the interesting behaviour is tested without a display.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from eco_print.gui.state import MIN_CROP_PT, Session
from eco_print.settings import Options

STATEMENTS = [f"statement-{n}" for n in "abcde"]


@pytest.fixture
def session(data_dir: Path):
    def build(stems: list[str] = (), options: Options | None = None) -> Session:
        s = Session(options=options or Options())
        if stems:
            s.add_paths([data_dir / f"{stem}.pdf" for stem in stems])
        return s

    return build


class TestReorderPrompt:
    """Whether Save should offer to enable minimise-pages first (#12).

    The three packing-* fixtures are the established case where reordering
    genuinely helps (3 sheets ordered, 2 reordered) -- the same fixtures
    UC-06's headline test and TestEffectsAreReal use.
    """

    PACKING = [f"packing-{n}" for n in "abc"]

    def test_offered_when_reorder_would_help(self, session):
        s = session(self.PACKING)
        assert s.should_offer_reorder() is True

    def test_not_offered_when_reorder_is_already_on(self, session):
        s = session(self.PACKING, Options(reorder=True))
        assert s.should_offer_reorder() is False

    def test_not_offered_when_reordering_would_not_help(self, session):
        """The five statements already pack optimally in order."""
        s = session(STATEMENTS)
        assert s.should_offer_reorder() is False

    def test_not_offered_with_nothing_loaded(self, session):
        assert session().should_offer_reorder() is False

    def test_declining_suppresses_the_prompt(self, session):
        s = session(self.PACKING)
        s.decline_reorder_prompt()
        assert s.should_offer_reorder() is False

    def test_declining_does_not_change_the_setting(self, session):
        s = session(self.PACKING)
        s.decline_reorder_prompt()
        assert s.options.reorder is False

    def test_a_list_change_after_declining_re_arms_the_prompt(self, session):
        s = session(self.PACKING)
        s.decline_reorder_prompt()
        assert s.should_offer_reorder() is False
        s.remove(0)                 # a genuine change, whatever its effect
        s.add_paths([Path("tests/data/packing-a.pdf")])
        assert s.reorder_prompt_dismissed_at != s.revision

    def test_an_irrelevant_setting_change_re_arms_the_prompt(self, session):
        """Confirms re-arming does not depend on the change altering the
        packing outcome -- only on the state having moved on at all."""
        s = session(self.PACKING)
        s.decline_reorder_prompt()
        before = s.estimate().reorder_would_save
        s.apply_options(replace(s.options, separator=True))
        assert s.estimate().reorder_would_save == before   # unaffected
        assert s.should_offer_reorder() is True             # but re-armed

    def test_a_repeated_decline_at_the_same_revision_is_idempotent(self, session):
        s = session(self.PACKING)
        s.decline_reorder_prompt()
        s.decline_reorder_prompt()
        assert s.should_offer_reorder() is False


class TestDirtyTracking:
    """UC-03: the close prompt fires only for real, unsaved changes.

    "Modified" here means anything that would change what Save PDF writes —
    the list, a crop, or a setting — not merely that documents are loaded.
    """

    def test_an_empty_session_is_not_dirty(self, session):
        assert session().dirty is False

    def test_adding_documents_makes_it_dirty(self, session):
        assert session(STATEMENTS).dirty is True

    def test_marking_saved_clears_it(self, session):
        s = session(STATEMENTS)
        s.mark_saved()
        assert s.dirty is False

    def test_a_further_change_after_saving_re_marks_it_dirty(self, session):
        """The state on disk no longer matches what's on screen."""
        s = session(STATEMENTS)
        s.mark_saved()
        s.remove(0)
        assert s.dirty is True

    def test_removing_every_document_after_saving_is_still_not_dirty(self, session):
        s = session(STATEMENTS)
        s.mark_saved()
        for _ in range(5):
            s.remove(0)
        assert s.dirty is False  # nothing left to lose

    def test_reordering_counts_as_a_modification(self, session):
        s = session(STATEMENTS)
        s.mark_saved()
        s.move(0, 4)
        assert s.dirty is True

    def test_editing_a_crop_counts_as_a_modification(self, session):
        """Confirmed: crops count, not just list membership."""
        s = session(STATEMENTS)
        s.mark_saved()
        s.set_manual_box(0, 800.0, 400.0)
        assert s.dirty is True

    def test_resetting_an_unmodified_crop_is_not_a_modification(self, session):
        """Nothing actually changed, so nothing should be marked dirty."""
        s = session(STATEMENTS)
        s.mark_saved()
        s.reset_to_auto(0)          # already auto; a no-op
        assert s.dirty is False

    def test_changing_a_setting_counts_as_a_modification(self, session):
        """Confirmed: settings count too, not just list membership."""
        s = session(STATEMENTS)
        s.mark_saved()
        s.apply_options(replace(s.options, gap=99.0))
        assert s.dirty is True

    def test_reapplying_the_same_settings_is_not_a_modification(self, session):
        s = session(STATEMENTS)
        s.mark_saved()
        s.apply_options(replace(s.options))
        assert s.dirty is False

    def test_clearing_an_empty_session_is_not_a_modification(self, session):
        s = session()
        s.mark_saved()
        s.clear()
        assert s.dirty is False

    def test_saving_again_after_a_second_change_clears_it_again(self, session):
        s = session(STATEMENTS)
        s.mark_saved()
        s.remove(0)
        s.mark_saved()
        assert s.dirty is False


class TestBuildingTheList:
    def test_dropping_files_adds_a_row_each(self, session):
        assert len(session(STATEMENTS).entries) == 5

    def test_dropping_a_folder_expands_it(self, statement_dir: Path):
        s = Session()
        s.add_paths([statement_dir])
        assert len(s.entries) == 5

    def test_every_page_of_a_document_becomes_a_row(self, session):
        assert len(session(["multipage"]).entries) == 3

    def test_the_same_file_twice_gives_two_rows(self, session, data_dir: Path):
        """Printing the same document twice is a legitimate wish (UC-03)."""
        s = session(["statement-a"])
        s.add_paths([data_dir / "statement-a.pdf"])
        assert len(s.entries) == 2

    def test_a_bad_file_is_recorded_not_raised(self, tmp_path: Path):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        s = Session()
        s.add_paths([bad])
        assert s.entries == []
        assert len(s.errors) == 1

    def test_valid_files_in_a_mixed_drop_still_arrive(self, tmp_path: Path, data_dir: Path):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        s = Session()
        s.add_paths([data_dir / "statement-a.pdf", bad])
        assert len(s.entries) == 1
        assert len(s.errors) == 1

    def test_a_blank_page_is_listed_but_contributes_nothing(self, session):
        s = session(["statement-a", "blank"])
        assert len(s.entries) == 2
        assert len(s.blocks()) == 1

    def test_rows_can_be_removed_and_reordered(self, session):
        s = session(STATEMENTS)
        s.remove(0)
        assert len(s.entries) == 4
        first = s.entries[0]
        s.move(0, 3)
        assert s.entries[3] is first

    def test_clearing_empties_everything(self, session):
        s = session(STATEMENTS)
        s.clear()
        assert s.entries == [] and s.errors == []


class TestEstimate:
    def test_the_five_statements_show_two_pages(self, session):
        estimate = session(STATEMENTS).estimate()
        assert (estimate.blocks, estimate.sheets, estimate.saved) == (5, 2, 3)
        assert "5 blocks -> 2 pages" in estimate.describe()

    def test_an_empty_list_says_so(self, session):
        assert session().estimate().describe() == "no documents yet"

    def test_the_estimate_follows_a_removal(self, session):
        s = session(STATEMENTS)
        for _ in range(3):
            s.remove(0)
        assert s.estimate().sheets == 1

    def test_a_worthwhile_reorder_is_advertised(self, session):
        """UC-06: the user sees the trade before ticking the box."""
        estimate = session([f"packing-{n}" for n in "abc"]).estimate()
        assert estimate.sheets == 3
        assert estimate.reorder_would_save == 1
        assert "would save 1" in estimate.describe()

    def test_a_pointless_reorder_is_not_advertised(self, session):
        estimate = session(STATEMENTS).estimate()
        assert estimate.reorder_would_save == 0
        assert "would save" not in estimate.describe()

    def test_ticking_reorder_reports_the_saving(self, session):
        s = session([f"packing-{n}" for n in "abc"])
        s.apply_options(replace(s.options, reorder=True))
        estimate = s.estimate()
        assert estimate.sheets == 2
        assert estimate.reorder_saved == 1


class TestManualCrops:
    def test_a_manual_box_overrides_detection(self, session):
        s = session(["statement-a"])
        detected = s.entries[0].height
        s.set_manual_box(0, 800.0, 400.0)
        assert s.entries[0].height == 400.0 != detected
        assert s.entries[0].is_manual

    def test_a_manual_box_changes_the_estimate(self, session):
        s = session(STATEMENTS)
        s.set_manual_box(0, 841.0, 100.0)
        assert s.estimate().sheets == 3

    def test_dragging_past_the_other_edge_cannot_invert_the_box(self, session):
        s = session(["statement-a"])
        box = s.set_manual_box(0, 200.0, 600.0)
        assert box.top > box.bottom

    def test_a_box_cannot_be_emptied(self, session):
        s = session(["statement-a"])
        box = s.set_manual_box(0, 500.0, 500.0)
        assert box.height >= MIN_CROP_PT

    def test_a_box_is_clamped_to_the_page(self, session):
        s = session(["statement-a"])
        box = s.set_manual_box(0, 9999.0, -9999.0)
        assert box.bottom == 0.0
        assert box.top == pytest.approx(s.entries[0].page.height)

    def test_a_crop_may_cover_the_whole_page(self, session):
        """Choosing to keep everything is allowed (UC-04)."""
        s = session(["with-footer"])
        page = s.entries[0].page
        box = s.set_manual_box(0, page.height, 0.0)
        assert box.height == pytest.approx(page.height)

    def test_reset_restores_exactly_what_was_detected(self, session):
        s = session(["statement-a"])
        detected = s.entries[0].height
        s.set_manual_box(0, 800.0, 400.0)
        s.reset_to_auto(0)
        assert s.entries[0].height == detected
        assert not s.entries[0].is_manual

    def test_reset_all_restores_every_row(self, session):
        s = session(STATEMENTS)
        for index in range(5):
            s.set_manual_box(index, 800.0, 300.0)
        s.reset_all_to_auto()
        assert not any(entry.is_manual for entry in s.entries)

    def test_apply_to_all_copies_one_crop_across_the_batch(self, session):
        """The common case: identically laid-out documents (UC-04)."""
        s = session(STATEMENTS)
        s.set_manual_box(0, 820.0, 500.0)
        changed = s.apply_box_to_all(0)
        assert changed == 4
        assert len({round(entry.height, 3) for entry in s.entries}) == 1

    def test_apply_to_all_leaves_differently_sized_pages_alone(self, session):
        """The same coordinates would mean something else on another size."""
        s = session(["statement-a", "landscape"])
        s.set_manual_box(0, 820.0, 500.0)
        assert s.apply_box_to_all(0) == 0
        assert not s.entries[1].is_manual

    def test_a_crop_survives_reordering(self, session):
        s = session(STATEMENTS)
        s.set_manual_box(0, 820.0, 500.0)
        entry = s.entries[0]
        s.move(0, 4)
        assert entry.is_manual and s.entries[4] is entry


class TestSettingsAffectTheList:
    def test_changing_padding_redetects(self, session):
        s = session(["statement-a"])
        before = s.entries[0].height
        s.apply_options(replace(s.options, pad=30.0))
        assert s.entries[0].height == pytest.approx(before + 48, abs=1)

    def test_full_ink_brings_a_footer_back(self, session):
        s = session(["with-footer"])
        assert s.entries[0].height < 300
        s.apply_options(replace(s.options, full_ink=True))
        assert s.entries[0].height > 700

    def test_a_manual_crop_is_not_overwritten_by_redetection(self, session):
        """An automatic setting must not undo a deliberate choice (UC-08)."""
        s = session(["statement-a"])
        s.set_manual_box(0, 800.0, 400.0)
        s.apply_options(replace(s.options, pad=30.0))
        assert s.entries[0].height == 400.0

    def test_a_packing_only_setting_does_not_redetect(self, session):
        s = session(["statement-a"])
        detection = s.entries[0].detection
        s.apply_options(replace(s.options, gap=40.0))
        assert s.entries[0].detection is detection


class TestDetails:
    """The Details pane's content, and why it exists (UC-03, UC-08).

    `--verbose` toggled `Options.verbose` in the GUI but nothing consumed it —
    the checkbox had no visible effect. `details()` is what closes that gap.
    """

    def test_an_empty_session_says_so(self, session):
        assert session().details() == "nothing to report yet"

    def test_each_page_is_reported(self, session):
        details = session(STATEMENTS).details()
        for name in STATEMENTS:
            assert f"{name}.pdf p1" in details

    def test_the_detected_height_and_method_appear(self, session):
        details = session(["with-footer"]).details()
        assert "213pt kept" in details
        assert "gap-cut" in details

    def test_a_manual_crop_is_reported_as_manual(self, session):
        s = session(["statement-a"])
        s.set_manual_box(0, 800.0, 400.0)
        details = s.details()
        assert "400pt kept (manual)" in details
        assert "ink-box" not in details

    def test_a_blank_page_is_reported_as_skipped(self, session):
        assert "blank, skipped" in session(["blank"]).details()

    def test_skipped_inputs_are_named_with_their_reason(self, tmp_path: Path):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        s = Session()
        s.add_paths([bad])
        details = s.details()
        assert "Skipped" in details
        assert "bad.pdf" in details

    def test_the_packing_outcome_is_reported_sheet_by_sheet(self, session):
        """The headline case: five documents, two sheets, 3 then 2."""
        details = session(STATEMENTS).details()
        assert "Packing (2 sheets)" in details
        assert "sheet 1: statement-a.pdf p1, statement-b.pdf p1, statement-c.pdf p1" in details
        assert "sheet 2: statement-d.pdf p1, statement-e.pdf p1" in details

    def test_a_single_sheet_is_not_pluralised(self, session):
        assert "Packing (1 sheet)" in session(["statement-a"]).details()

    def test_an_oversized_block_is_warned_about(self, session):
        assert "taller than one sheet" in session(["oversized"]).details()

    def test_details_follow_a_settings_change(self, session):
        """Detection details must reflect the live options, not a stale run."""
        s = session(["with-footer"])
        assert "gap-cut" in s.details()
        s.apply_options(replace(s.options, full_ink=True))
        assert "full-ink" in s.details()
        assert "gap-cut" not in s.details()


class TestCommandLineTransfer:
    def test_the_line_names_each_document_once(self, session, data_dir: Path):
        s = session(["multipage"])
        assert s.command_line(Path("out.pdf")).count("multipage.pdf") == 1

    def test_changed_settings_appear_as_flags(self, session):
        s = session(["statement-a"], Options(reorder=True, gap=30.0))
        line = s.command_line(Path("out.pdf"))
        assert "--reorder" in line and "--gap 30" in line

    def test_default_settings_add_no_flags(self, session):
        line = session(["statement-a"]).command_line(Path("out.pdf"))
        assert "--" not in line

    def test_manual_crops_are_declared_unreproducible(self, session):
        """UC-08: the button must not promise more than flags can deliver."""
        s = session(["statement-a"])
        s.set_manual_box(0, 800.0, 400.0)
        assert "manual crops are not reproduced" in s.command_line(Path("out.pdf"))

    def test_paths_with_spaces_are_quoted(self, tmp_path: Path, data_dir: Path):
        folder = tmp_path / "my documents"
        folder.mkdir()
        target = folder / "statement-a.pdf"
        target.write_bytes((data_dir / "statement-a.pdf").read_bytes())
        s = Session()
        s.add_paths([target])
        assert "'" in s.command_line(Path("out.pdf"))


class TestEquivalenceWithTheCli:
    def test_the_same_settings_give_the_same_bytes(self, tmp_path: Path, data_dir: Path):
        """UC-08: neither front end is a different program."""
        from eco_print.compose import write
        from eco_print.pipeline import run

        options = Options(reorder=True, separator=True)
        paths = [data_dir / f"{stem}.pdf" for stem in STATEMENTS]

        cli_output = tmp_path / "cli.pdf"
        run(paths, cli_output, options)

        s = Session(options=options)
        s.add_paths(paths)
        gui_output = tmp_path / "gui.pdf"
        write(s.packing(), gui_output, options)

        assert cli_output.read_bytes() == gui_output.read_bytes()

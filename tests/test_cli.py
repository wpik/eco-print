"""The command-line front end, as far as M1 and M2 take it.

Argument handling, output-path safety and load reporting are complete here; the
assertions about a written document arrive with M4-M5.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from eco_print import __version__
from eco_print.cli import EXIT_FAILED, EXIT_OK, EXIT_PARTIAL, build_parser, main


class TestInvocation:
    def test_version_is_reported(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        assert __version__ in capsys.readouterr().out

    def test_help_lists_run_flags_and_options_together(self):
        help_text = build_parser().format_help()
        for flag in ("--force", "--dry-run", "--margin", "--reorder", "--recursive"):
            assert flag in help_text

    def test_no_arguments_points_at_the_gui(self, capsys):
        assert main([]) == EXIT_FAILED
        assert "graphical interface" in capsys.readouterr().err

    def test_a_lone_path_is_rejected(self, statement_dir: Path):
        """One path is ambiguous: it names neither an input nor an output."""
        with pytest.raises(SystemExit) as exc:
            main([str(statement_dir)])
        assert exc.value.code != 0


class TestOutputSafety:
    def test_an_existing_output_is_refused(self, statement_dir: Path, tmp_path: Path):
        output = tmp_path / "out.pdf"
        output.write_bytes(b"%PDF-1.4\n")
        with pytest.raises(SystemExit) as exc:
            main([str(statement_dir), str(output)])
        assert exc.value.code != 0

    def test_force_allows_overwriting(self, statement_dir: Path, tmp_path: Path):
        output = tmp_path / "out.pdf"
        output.write_bytes(b"%PDF-1.4\n")
        assert main([str(statement_dir), str(output), "--force"]) == EXIT_OK

    def test_dry_run_does_not_object_to_an_existing_output(
        self, statement_dir: Path, tmp_path: Path
    ):
        output = tmp_path / "out.pdf"
        output.write_bytes(b"%PDF-1.4\n")
        assert main([str(statement_dir), str(output), "--dry-run"]) == EXIT_OK

    def test_a_non_pdf_output_is_refused(self, statement_dir: Path, tmp_path: Path):
        with pytest.raises(SystemExit):
            main([str(statement_dir), str(tmp_path / "out.txt")])

    def test_a_missing_output_directory_is_created_one_level_deep(
        self, statement_dir: Path, tmp_path: Path
    ):
        output = tmp_path / "new" / "out.pdf"
        assert main([str(statement_dir), str(output)]) == EXIT_OK
        assert output.parent.is_dir()

    def test_a_missing_output_grandparent_is_an_error(
        self, statement_dir: Path, tmp_path: Path
    ):
        with pytest.raises(SystemExit):
            main([str(statement_dir), str(tmp_path / "a" / "b" / "out.pdf")])


class TestReporting:
    def test_a_clean_run_reports_what_it_loaded(self, statement_dir: Path, tmp_path):
        code = main([str(statement_dir), str(tmp_path / "out.pdf")])
        assert code == EXIT_OK

    def test_a_skipped_input_is_named_and_changes_the_exit_code(
        self, statement_dir: Path, tmp_path: Path, capsys
    ):
        """UC-07: a partial run is distinguishable from a clean one."""
        (statement_dir / "impostor.pdf").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        code = main([str(statement_dir), str(tmp_path / "out.pdf")])
        assert code == EXIT_PARTIAL
        assert "impostor.pdf" in capsys.readouterr().err

    def test_nothing_readable_fails_outright(self, tmp_path: Path, capsys):
        """A zero-page document is worse than no document."""
        empty = tmp_path / "sources"
        empty.mkdir()
        assert main([str(empty), str(tmp_path / "out.pdf")]) == EXIT_FAILED
        assert "nothing to do" in capsys.readouterr().err

    def test_verbose_describes_each_page(self, statement_dir: Path, tmp_path, capsys):
        main([str(statement_dir), str(tmp_path / "out.pdf"), "-v"])
        assert "statement-a.pdf p1" in capsys.readouterr().out


class TestOptionsReachTheRun:
    def test_recursive_changes_what_is_loaded(
        self, statement_dir: Path, tmp_path: Path, data_dir: Path, capsys
    ):
        import shutil

        nested = statement_dir / "more"
        nested.mkdir()
        shutil.copy(data_dir / "landscape.pdf", nested / "landscape.pdf")

        main([str(statement_dir), str(tmp_path / "shallow.pdf"), "-v"])
        assert "landscape.pdf" not in capsys.readouterr().out

        main([str(statement_dir), str(tmp_path / "deep.pdf"), "-v", "--recursive"])
        assert "landscape.pdf" in capsys.readouterr().out


class TestWritingAnOutput:
    """M5: the command line does the whole job (UC-01)."""

    def test_the_five_statements_become_a_two_page_pdf(
        self, statement_dir: Path, tmp_path: Path, capsys
    ):
        from pypdf import PdfReader

        output = tmp_path / "combined.pdf"
        assert main([str(statement_dir), str(output)]) == EXIT_OK
        assert len(PdfReader(str(output)).pages) == 2
        assert "5 blocks from 5 documents -> 2 pages" in capsys.readouterr().out

    def test_explicit_files_work_like_a_directory(
        self, statement_dir: Path, tmp_path: Path
    ):
        from pypdf import PdfReader

        files = sorted(str(p) for p in statement_dir.glob("*.pdf"))
        output = tmp_path / "explicit.pdf"
        assert main([*files, str(output)]) == EXIT_OK
        assert len(PdfReader(str(output)).pages) == 2

    def test_the_saving_is_reported(self, statement_dir: Path, tmp_path: Path, capsys):
        main([str(statement_dir), str(tmp_path / "out.pdf")])
        assert "saved 3 sheets" in capsys.readouterr().out

    def test_a_dry_run_writes_nothing(self, statement_dir: Path, tmp_path: Path, capsys):
        output = tmp_path / "out.pdf"
        assert main([str(statement_dir), str(output), "--dry-run"]) == EXIT_OK
        assert not output.exists()
        assert "was not written" in capsys.readouterr().out

    def test_reorder_reports_what_it_saved(self, data_dir: Path, tmp_path: Path, capsys):
        """UC-06: the flag says whether it actually bought anything."""
        packing = [str(data_dir / f"packing-{n}.pdf") for n in "abc"]
        main([*packing, str(tmp_path / "out.pdf"), "--reorder"])
        out = capsys.readouterr().out
        assert "-> 2 pages" in out
        assert "--reorder saved 1" in out

    def test_without_reorder_the_same_files_need_three_pages(
        self, data_dir: Path, tmp_path: Path, capsys
    ):
        packing = [str(data_dir / f"packing-{n}.pdf") for n in "abc"]
        main([*packing, str(tmp_path / "out.pdf")])
        assert "-> 3 pages" in capsys.readouterr().out

    def test_settings_reach_the_output(self, statement_dir: Path, tmp_path: Path):
        from pypdf import PdfReader

        output = tmp_path / "letter.pdf"
        main([str(statement_dir), str(output), "--page-size", "letter"])
        page = PdfReader(str(output)).pages[0]
        assert float(page.mediabox.width) == pytest.approx(612.0)

    def test_a_blank_page_is_skipped_not_printed(self, data_dir: Path, tmp_path: Path, capsys):
        from pypdf import PdfReader

        output = tmp_path / "out.pdf"
        code = main([
            str(data_dir / "statement-a.pdf"), str(data_dir / "blank.pdf"), str(output)
        ])
        assert code == EXIT_OK
        assert len(PdfReader(str(output)).pages) == 1
        assert "blank" in capsys.readouterr().err

    def test_an_oversized_block_is_warned_about(self, data_dir: Path, tmp_path: Path, capsys):
        main([str(data_dir / "oversized.pdf"), str(tmp_path / "out.pdf")])
        assert "taller than one sheet" in capsys.readouterr().err

    def test_a_batch_survives_one_bad_file(
        self, statement_dir: Path, tmp_path: Path, capsys
    ):
        """UC-07: the good files still produce their output, exit code says partial."""
        from pypdf import PdfReader

        (statement_dir / "impostor.pdf").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        output = tmp_path / "out.pdf"
        assert main([str(statement_dir), str(output)]) == EXIT_PARTIAL
        assert len(PdfReader(str(output)).pages) == 2
        assert "impostor.pdf" in capsys.readouterr().err

    def test_nothing_is_written_when_everything_fails(self, tmp_path: Path):
        """A zero-page PDF is worse than no PDF (UC-07)."""
        sources = tmp_path / "sources"
        sources.mkdir()
        (sources / "bad.pdf").write_bytes(b"not a pdf")
        output = tmp_path / "out.pdf"
        assert main([str(sources), str(output)]) == EXIT_FAILED
        assert not output.exists()

    def test_only_blank_pages_produce_no_document(self, data_dir: Path, tmp_path: Path):
        output = tmp_path / "out.pdf"
        assert main([str(data_dir / "blank.pdf"), str(output)]) == EXIT_FAILED
        assert not output.exists()

    def test_rerunning_is_reproducible(self, statement_dir: Path, tmp_path: Path):
        first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
        main([str(statement_dir), str(first)])
        main([str(statement_dir), str(second)])
        assert first.read_bytes() == second.read_bytes()

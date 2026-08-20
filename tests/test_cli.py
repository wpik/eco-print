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

        main([str(statement_dir), str(tmp_path / "out.pdf"), "-v"])
        assert "landscape.pdf" not in capsys.readouterr().out

        main([str(statement_dir), str(tmp_path / "out.pdf"), "-v", "--recursive"])
        assert "landscape.pdf" in capsys.readouterr().out

"""Resolving inputs and opening documents (UC-02, UC-07)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from eco_print.loader import expand_inputs, load, load_pages


class TestExpandInputs:
    def test_a_file_is_taken_as_given(self, data_dir: Path):
        target = data_dir / "statement-a.pdf"
        assert expand_inputs([target]) == [target]

    def test_a_directory_yields_its_pdfs_sorted_by_name(self, statement_dir: Path):
        found = expand_inputs([statement_dir])
        assert [p.name for p in found] == [
            f"statement-{n}.pdf" for n in "abcde"
        ]

    def test_sorting_is_case_insensitive(self, tmp_path: Path, data_dir: Path):
        for name in ("Beta.pdf", "alpha.pdf", "Gamma.pdf"):
            shutil.copy(data_dir / "blank.pdf", tmp_path / name)
        assert [p.name for p in expand_inputs([tmp_path])] == [
            "alpha.pdf", "Beta.pdf", "Gamma.pdf"
        ]

    def test_non_pdfs_and_hidden_files_are_ignored(self, statement_dir: Path):
        (statement_dir / "notes.txt").write_text("not a pdf")
        (statement_dir / ".hidden.pdf").write_bytes(b"%PDF-1.4\n")
        assert len(expand_inputs([statement_dir])) == 5

    def test_directories_are_not_scanned_recursively_by_default(
        self, statement_dir: Path, data_dir: Path
    ):
        nested = statement_dir / "more"
        nested.mkdir()
        shutil.copy(data_dir / "blank.pdf", nested / "blank.pdf")
        assert len(expand_inputs([statement_dir])) == 5
        assert len(expand_inputs([statement_dir], recursive=True)) == 6

    def test_files_and_directories_keep_their_command_line_order(
        self, statement_dir: Path, data_dir: Path
    ):
        """Each argument's expansion is spliced in where the argument sat."""
        extra = data_dir / "landscape.pdf"
        found = expand_inputs([extra, statement_dir])
        assert found[0] == extra
        assert [p.name for p in found[1:]] == [
            f"statement-{n}.pdf" for n in "abcde"
        ]

    def test_the_output_file_is_never_an_input(self, statement_dir: Path):
        """Otherwise re-running a command would feed its own result back in."""
        output = statement_dir / "statement-c.pdf"
        found = expand_inputs([statement_dir], output=output)
        assert output.resolve() not in [p.resolve() for p in found]
        assert len(found) == 4

    def test_the_output_is_excluded_by_identity_not_by_name(
        self, statement_dir: Path, tmp_path: Path
    ):
        """A same-named file in another directory is a different file."""
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        decoy = elsewhere / "statement-c.pdf"
        shutil.copy(statement_dir / "statement-c.pdf", decoy)
        found = expand_inputs([statement_dir], output=decoy)
        assert len(found) == 5

    def test_an_empty_directory_yields_nothing(self, tmp_path: Path):
        assert expand_inputs([tmp_path]) == []


class TestLoadPages:
    def test_a_single_page_document_yields_one_page(self, data_dir: Path):
        result = load_pages([data_dir / "statement-a.pdf"])
        assert len(result.pages) == 1
        assert result.ok

    def test_page_geometry_is_reported_in_points(self, data_dir: Path):
        page = load_pages([data_dir / "statement-a.pdf"]).pages[0]
        assert page.width == pytest.approx(595.275, abs=0.01)
        assert page.height == pytest.approx(841.889, abs=0.01)

    def test_every_page_of_a_document_becomes_its_own_page(self, data_dir: Path):
        """UC-05: multi-page inputs are not truncated to the first page."""
        result = load_pages([data_dir / "multipage.pdf"])
        assert [p.page_index for p in result.pages] == [0, 1, 2]

    def test_landscape_geometry_survives(self, data_dir: Path):
        page = load_pages([data_dir / "landscape.pdf"]).pages[0]
        assert page.width > page.height

    def test_pages_are_labelled_for_the_user(self, data_dir: Path):
        page = load_pages([data_dir / "multipage.pdf"]).pages[1]
        assert page.label == "multipage.pdf p2"

    def test_document_count_counts_documents_not_pages(self, data_dir: Path):
        result = load_pages([data_dir / "multipage.pdf", data_dir / "blank.pdf"])
        assert len(result.pages) == 4
        assert result.document_count == 2


class TestEncryption:
    def test_an_empty_user_password_opens_without_being_asked(self, data_dir: Path):
        """UC-07: the common bank-document case must just work."""
        result = load_pages([data_dir / "encrypted.pdf"])
        assert result.ok
        assert len(result.pages) == 1
        assert result.pages[0].password == ""

    def test_an_unencrypted_document_carries_no_password(self, data_dir: Path):
        assert load_pages([data_dir / "statement-a.pdf"]).pages[0].password is None


class TestResilience:
    """One bad input must never lose a batch (UC-07)."""

    def test_a_missing_file_is_reported_not_raised(self, tmp_path: Path):
        result = load_pages([tmp_path / "nope.pdf"])
        assert result.pages == []
        assert "no such file" in result.errors[0].reason

    def test_a_renamed_jpeg_is_skipped_by_name(
        self, statement_dir: Path, data_dir: Path
    ):
        impostor = statement_dir / "statement-f.pdf"
        impostor.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 200)  # JPEG header
        result = load([statement_dir])
        assert len(result.pages) == 5
        assert [e.path.name for e in result.errors] == ["statement-f.pdf"]
        assert not result.ok

    def test_a_truncated_pdf_is_skipped(self, tmp_path: Path, data_dir: Path):
        broken = tmp_path / "broken.pdf"
        broken.write_bytes((data_dir / "statement-a.pdf").read_bytes()[:400])
        result = load_pages([broken])
        assert result.pages == []
        assert result.errors

    def test_an_empty_file_is_skipped(self, tmp_path: Path):
        empty = tmp_path / "empty.pdf"
        empty.write_bytes(b"")
        assert load_pages([empty]).errors

    def test_a_failure_does_not_disturb_the_others_order(
        self, data_dir: Path, tmp_path: Path
    ):
        broken = tmp_path / "broken.pdf"
        broken.write_bytes(b"not a pdf at all")
        result = load_pages([
            data_dir / "statement-a.pdf", broken, data_dir / "statement-b.pdf"
        ])
        assert [p.path.name for p in result.pages] == [
            "statement-a.pdf", "statement-b.pdf"
        ]
        assert len(result.errors) == 1


class TestLoad:
    def test_expansion_and_loading_together(self, statement_dir: Path):
        result = load([statement_dir])
        assert len(result.pages) == 5
        assert result.document_count == 5
        assert result.ok

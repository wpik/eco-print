"""The options declaration and its two derived front ends (UC-08)."""
from __future__ import annotations

import argparse
from dataclasses import fields

import pytest

from eco_print.settings import (
    GUI_BEHAVIOUR_FLAGS,
    PAGE_SIZES,
    Options,
    add_options,
)


def parse(argv: list[str]) -> Options:
    parser = add_options(argparse.ArgumentParser())
    return Options.from_namespace(parser.parse_args(argv))


class TestDeclaration:
    def test_every_field_declares_its_metadata(self):
        """A field without metadata could not reach either front end."""
        for f in fields(Options):
            meta = f.metadata
            assert meta, f"{f.name} declares no option metadata"
            for key in ("flag", "help", "control", "label"):
                assert meta[key], f"{f.name} is missing {key}"
            assert meta["control"] in ("spin", "check", "combo")

    def test_flags_are_unique(self):
        flags = [f.metadata["flag"] for f in fields(Options)]
        assert len(flags) == len(set(flags))

    def test_combo_choices_are_valid_defaults(self):
        defaults = Options()
        for f in fields(Options):
            if f.metadata["control"] == "combo":
                assert getattr(defaults, f.name) in f.metadata["choices"]

    def test_spin_defaults_are_within_range(self):
        defaults = Options()
        for f in fields(Options):
            if f.metadata["control"] != "spin":
                continue
            value = getattr(defaults, f.name)
            assert f.metadata["minimum"] <= value <= f.metadata["maximum"]


class TestGeneratedParser:
    def test_defaults_match_the_dataclass(self):
        assert parse([]) == Options()

    def test_rejects_an_unknown_page_size(self):
        with pytest.raises(SystemExit):
            parse(["--page-size", "a3"])


class TestDerivedGeometry:
    def test_usable_height_takes_both_margins(self):
        options = Options(margin=28.0)
        assert options.usable_height() == pytest.approx(841.889 - 56)

    def test_page_dimensions_follow_the_choice(self):
        assert Options(page_size="letter").page_dimensions() == PAGE_SIZES["letter"]


class TestCopyAsCommandLine:
    """`to_cli_args` backs the GUI's transfer to the terminal (UC-08)."""

    def test_defaults_produce_no_flags(self):
        assert Options().to_cli_args() == []

    def test_only_changed_settings_appear(self):
        assert Options(gap=30.0).to_cli_args() == ["--gap", "30"]

    def test_booleans_appear_as_bare_flags(self):
        assert Options(reorder=True).to_cli_args() == ["--reorder"]

    def test_whole_numbers_lose_their_decimal_point(self):
        assert "28.0" not in " ".join(Options(margin=28.5, gap=40.0).to_cli_args())

    def test_the_result_round_trips_through_the_parser(self):
        """What the GUI hands over must reproduce the GUI's own settings."""
        original = Options(
            margin=10.0, gap=33.5, pad=0.0, page_size="letter",
            full_ink=True, separator=True, reorder=True, recursive=True,
            verbose=True,
        )
        assert parse(original.to_cli_args()) == original

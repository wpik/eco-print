"""The single declaration of every option the tool offers (UC-08).

Both front ends are *generated* from `Options`: `build_parser` walks the fields
to build the argparse parser, and the GUI settings panel walks the same fields to
build its widgets. An option therefore cannot exist in one front end and not the
other, and their help texts cannot disagree.

Three CLI flags are deliberately absent from `Options` because they concern the
run rather than the output, and the GUI satisfies them by its nature rather than
with a widget. They are listed in `GUI_BEHAVIOUR_FLAGS`, and that list is closed:
a test asserts its exact contents so a new option cannot quietly be excused from
parity by being added to it.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, fields
from typing import Any

# Sheet sizes in PDF points (1/72 inch).
PAGE_SIZES: dict[str, tuple[float, float]] = {
    "a4": (595.275, 841.889),
    "letter": (612.0, 792.0),
}

#: Options satisfied in the GUI by behaviour rather than a control (UC-08).
#: Closed list — see the module docstring.
GUI_BEHAVIOUR_FLAGS: tuple[str, ...] = ("--force", "--dry-run", "output path")


def option(
    flag: str,
    help: str,
    control: str,
    *,
    short: str | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    choices: tuple[str, ...] | None = None,
    unit: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Metadata for one option, consumed by both front ends.

    `control` is the GUI widget kind: "spin", "check" or "combo".
    `label` is the GUI wording, which may differ from the CLI help: a flag reads
    as an instruction, a checkbox reads as a state.
    """
    if control not in ("spin", "check", "combo"):
        raise ValueError(f"unknown control kind: {control}")
    return {
        "flag": flag,
        "short": short,
        "help": help,
        "control": control,
        "minimum": minimum,
        "maximum": maximum,
        "choices": choices,
        "unit": unit,
        "label": label or help,
    }


@dataclass
class Options:
    """Everything that changes the content of the output.

    The pipeline takes this and its inputs; nothing downstream reads argparse or
    Qt. Because both front ends produce the same `Options`, identical settings
    giving identical output is structural rather than a coincidence.
    """

    margin: float = field(
        default=28.0,
        metadata=option(
            "--margin", "outer margin of the sheet, in points", "spin",
            minimum=0.0, maximum=200.0, unit="pt", label="sheet margin",
        ),
    )
    gap: float = field(
        default=20.0,
        metadata=option(
            "--gap", "minimum vertical space between blocks, in points", "spin",
            minimum=0.0, maximum=200.0, unit="pt", label="gap between documents",
        ),
    )
    pad: float = field(
        default=6.0,
        metadata=option(
            "--pad", "whitespace kept around detected content, in points", "spin",
            minimum=0.0, maximum=72.0, unit="pt", label="padding around content",
        ),
    )
    page_size: str = field(
        default="a4",
        metadata=option(
            "--page-size", "output sheet size", "combo",
            choices=tuple(PAGE_SIZES), label="sheet size",
        ),
    )
    full_ink: bool = field(
        default=False,
        metadata=option(
            "--full-ink", "keep the whole ink area; never drop trailing footers", "check",
            label="keep footers and page numbers",
        ),
    )
    separator: bool = field(
        default=False,
        metadata=option(
            "--separator", "draw a dashed cut line between blocks on a sheet", "check",
            label="add horizontal line between documents",
        ),
    )
    reorder: bool = field(
        default=False,
        metadata=option(
            "--reorder", "give up input order in exchange for the fewest sheets", "check",
            label="minimise pages (ignore order)",
        ),
    )
    recursive: bool = field(
        default=False,
        metadata=option(
            "--recursive", "descend into subdirectories of directory inputs", "check",
            label="scan folders recursively",
        ),
    )
    verbose: bool = field(
        default=False,
        metadata=option(
            "-v", "report what was detected and what was dropped", "check",
            short="--verbose", label="show detection details",
        ),
    )

    def page_dimensions(self) -> tuple[float, float]:
        """The output sheet size in points."""
        return PAGE_SIZES[self.page_size]

    def usable_height(self) -> float:
        """Sheet height available to blocks, once margins are taken."""
        return self.page_dimensions()[1] - 2 * self.margin

    # -- transfer between front ends (UC-08) --------------------------------

    def to_cli_args(self) -> list[str]:
        """The flags reproducing these settings, omitting anything at default.

        Backs the GUI's "copy as command line": a user tunes the settings by eye,
        then takes the invocation away to automate it.
        """
        args: list[str] = []
        for f in fields(self):
            value = getattr(self, f.name)
            if value == f.default:
                continue
            flag = f.metadata["flag"]
            if f.type is bool or isinstance(value, bool):
                args.append(flag)
            else:
                args += [flag, _format_number(value)]
        return args

    @classmethod
    def from_namespace(cls, ns: argparse.Namespace) -> "Options":
        """Collect the option fields out of a parsed command line."""
        return cls(**{f.name: getattr(ns, f.name) for f in fields(cls)})


def _format_number(value: Any) -> str:
    """Render a number without a pointless trailing `.0`."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def add_options(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Add every field of `Options` to a parser, deriving each from its metadata."""
    defaults = Options()
    for f in fields(Options):
        meta = f.metadata
        flags = [meta["flag"]] + ([meta["short"]] if meta["short"] else [])
        default = getattr(defaults, f.name)
        if meta["control"] == "check":
            parser.add_argument(
                *flags, dest=f.name, action="store_true", default=default,
                help=meta["help"],
            )
        elif meta["control"] == "combo":
            parser.add_argument(
                *flags, dest=f.name, choices=meta["choices"], default=default,
                help=f"{meta['help']} (default: {default})",
            )
        else:
            parser.add_argument(
                *flags, dest=f.name, type=float, default=default,
                metavar=(meta["unit"] or "N").upper(),
                help=f"{meta['help']} (default: {_format_number(default)})",
            )
    return parser

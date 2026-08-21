"""The whole job, end to end, independent of any front end.

Both the CLI and the GUI drive this: `load -> detect -> pack -> compose`. Because
they hand it the same `Options`, the same inputs give the same output whichever
way the tool was started (UC-08).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .compose import write
from .detect import Detection, detect_all
from .loader import load
from .model import Block, SourceError
from .packer import PackResult, pack
from .settings import Options


@dataclass
class RunResult:
    """Everything a front end needs to report on a run."""

    detections: list[Detection] = field(default_factory=list)
    packing: PackResult | None = None
    errors: list[SourceError] = field(default_factory=list)
    output: Path | None = None

    @property
    def blocks(self) -> list[Block]:
        return [Block(d.page, d.box) for d in self.detections if d.box is not None]

    @property
    def blank_pages(self) -> list[Detection]:
        return [d for d in self.detections if d.box is None]

    @property
    def document_count(self) -> int:
        return len({d.page.path for d in self.detections})

    @property
    def sheet_count(self) -> int:
        return self.packing.sheet_count if self.packing else 0

    @property
    def block_count(self) -> int:
        return len(self.blocks)

    @property
    def sheets_saved(self) -> int:
        """Sheets saved against printing every source page on its own sheet."""
        return max(self.block_count - self.sheet_count, 0)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        """The one line a run prints when it worked (UC-01)."""
        line = (
            f"{self.block_count} blocks from {self.document_count} documents "
            f"-> {self.sheet_count} pages"
        )
        if self.sheets_saved:
            line += f" (saved {self.sheets_saved} sheets)"
        if self.packing and self.packing.reorder_saved:
            line += (
                f"; ordered packing would use "
                f"{self.packing.alternative_sheets}, --reorder saved "
                f"{self.packing.reorder_saved}"
            )
        return line


def run(
    inputs: list[Path],
    output: Path | None,
    options: Options | None = None,
    write_output: bool = True,
) -> RunResult:
    """Load, detect, pack and — unless this is a dry run — write.

    Failures at every stage are collected rather than raised: one bad input must
    not lose the batch (UC-07).
    """
    options = options or Options()

    loaded = load(inputs, output=output, recursive=options.recursive)
    detected = detect_all(loaded.pages, options)

    result = RunResult(
        detections=detected.detections,
        errors=loaded.errors + detected.errors,
    )
    if not result.blocks:
        return result

    result.packing = pack(result.blocks, options)

    if write_output and output is not None:
        result.output = write(result.packing, output, options)
    return result

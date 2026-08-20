"""The types the pipeline passes between its stages.

    loader  -> SourcePage
    detect  -> Block (a SourcePage plus its ContentBox)
    packer  -> Sheet, PackResult
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourcePage:
    """One page of one input document, ready to be rendered or copied.

    `password` is what the file was opened with — the empty string for the
    common owner-password-only case (UC-07). Later stages reopen the file with
    it rather than repeating the discovery.
    """

    path: Path
    page_index: int          # 0-based
    width: float             # points
    height: float            # points
    password: str | None = None

    @property
    def label(self) -> str:
        """How this page is named to the user."""
        return f"{self.path.name} p{self.page_index + 1}"


@dataclass(frozen=True)
class ContentBox:
    """The region of a source page worth printing, in PDF points.

    Coordinates are PDF-native: the origin is the bottom-left of the page and y
    grows upwards, so `top` is the larger number.
    """

    left: float
    bottom: float
    right: float
    top: float
    origin: str = "auto"     # "auto" | "manual" | "full-ink"

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom


@dataclass(frozen=True)
class Block:
    """A source page cropped to its content box — the unit that gets packed."""

    page: SourcePage
    box: ContentBox

    @property
    def width(self) -> float:
        return self.box.width

    @property
    def height(self) -> float:
        return self.box.height


@dataclass(frozen=True)
class SourceError:
    """One input that could not be used, and why.

    Carried alongside the successes rather than raised: one bad file must never
    lose a batch (UC-07).
    """

    path: Path
    reason: str


@dataclass
class LoadResult:
    """What a load produced: the usable pages, and what was skipped."""

    pages: list[SourcePage]
    errors: list[SourceError]

    @property
    def ok(self) -> bool:
        """True when every input was processed."""
        return not self.errors

    @property
    def document_count(self) -> int:
        """How many distinct documents contributed pages."""
        return len({page.path for page in self.pages})

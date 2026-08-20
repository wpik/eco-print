"""The GUI's model, with no Qt in it (UC-03, UC-04).

Everything the window does to a document list happens here: adding, removing,
reordering, overriding a crop, and asking what the current settings would
produce. Keeping it free of Qt means the interesting behaviour is testable
without a display server, and the window is left as glue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..detect import Detection, detect
from ..loader import expand_inputs, load_pages
from ..model import Block, ContentBox, SourceError, SourcePage
from ..packer import PackResult, pack
from ..settings import Options

#: The smallest crop a user may drag to, in points.
MIN_CROP_PT = 8.0


@dataclass
class Entry:
    """One row of the document list: a page, its box, and how the box was set."""

    page: SourcePage
    detection: Detection
    manual_box: ContentBox | None = None

    @property
    def box(self) -> ContentBox | None:
        """The box actually used: a manual override, else what was detected."""
        return self.manual_box or self.detection.box

    @property
    def is_manual(self) -> bool:
        return self.manual_box is not None

    @property
    def is_blank(self) -> bool:
        return self.box is None

    @property
    def height(self) -> float:
        box = self.box
        return box.height if box else 0.0

    @property
    def label(self) -> str:
        return self.page.label

    def as_block(self) -> Block | None:
        box = self.box
        return Block(self.page, box) if box else None


@dataclass
class Estimate:
    """What the current list and settings would produce."""

    blocks: int = 0
    sheets: int = 0
    saved: int = 0
    reorder_saved: int = 0
    reorder_would_save: int = 0

    def describe(self) -> str:
        """The status line (UC-03)."""
        if not self.blocks:
            return "no documents yet"
        line = f"{self.blocks} blocks -> {self.sheets} pages"
        if self.saved:
            line += f" (saves {self.saved} sheets)"
        if self.reorder_saved:
            line += f"; minimising saved {self.reorder_saved}"
        elif self.reorder_would_save:
            line += f"; minimising pages would save {self.reorder_would_save}"
        return line


@dataclass
class Session:
    """The document list and the settings applied to it."""

    options: Options = field(default_factory=Options)
    entries: list[Entry] = field(default_factory=list)
    errors: list[SourceError] = field(default_factory=list)

    # -- building the list --------------------------------------------------

    def add_paths(self, paths: list[Path]) -> list[Entry]:
        """Add every page of every PDF in `paths`. Folders expand (UC-02).

        Dropping a file already in the list adds a second, independent entry:
        printing the same document twice is a legitimate wish (UC-03).
        """
        expanded = expand_inputs(list(paths), recursive=self.options.recursive)
        loaded = load_pages(expanded)
        self.errors.extend(loaded.errors)

        added: list[Entry] = []
        for page in loaded.pages:
            try:
                detection = detect(page, self.options)
            except Exception as exc:  # a bad page must not lose the drop
                self.errors.append(SourceError(page.path, str(exc)))
                continue
            entry = Entry(page=page, detection=detection)
            self.entries.append(entry)
            added.append(entry)
        return added

    def remove(self, index: int) -> None:
        del self.entries[index]

    def move(self, index: int, destination: int) -> None:
        """Reorder by dragging. Output order follows list order (UC-03)."""
        entry = self.entries.pop(index)
        self.entries.insert(max(0, min(destination, len(self.entries))), entry)

    def clear(self) -> None:
        self.entries.clear()
        self.errors.clear()

    # -- crops (UC-04) ------------------------------------------------------

    def set_manual_box(self, index: int, top: float, bottom: float) -> ContentBox:
        """Override one entry's crop, in PDF points.

        The edges are clamped to the page and ordered, so a drag past the
        opposite edge cannot invert or empty the box.
        """
        entry = self.entries[index]
        page = entry.page
        top, bottom = max(top, bottom), min(top, bottom)
        top = min(top, page.height)
        bottom = max(bottom, 0.0)
        if top - bottom < MIN_CROP_PT:
            bottom = max(0.0, top - MIN_CROP_PT)
        box = ContentBox(0.0, bottom, page.width, top, origin="manual")
        entry.manual_box = box
        return box

    def reset_to_auto(self, index: int) -> None:
        self.entries[index].manual_box = None

    def reset_all_to_auto(self) -> None:
        for entry in self.entries:
            entry.manual_box = None

    def apply_box_to_all(self, index: int) -> int:
        """Copy one entry's crop to every page of the same size (UC-04).

        The common case is a batch of identically laid-out documents, where one
        adjustment should serve them all. Pages of a different size are left
        alone: the same coordinates would mean something else on them.
        """
        source = self.entries[index]
        box = source.box
        if box is None:
            return 0

        changed = 0
        for position, entry in enumerate(self.entries):
            if position == index:
                continue
            if (entry.page.width, entry.page.height) != (
                source.page.width, source.page.height
            ):
                continue
            self.set_manual_box(position, box.top, box.bottom)
            changed += 1
        return changed

    # -- reacting to settings -----------------------------------------------

    def redetect(self) -> None:
        """Re-run detection after a change to `pad` or `full_ink` (UC-08).

        Entries the user cropped by hand keep their boxes: an automatic setting
        must not overwrite a deliberate choice.
        """
        for entry in self.entries:
            if entry.is_manual:
                continue
            try:
                entry.detection = detect(entry.page, self.options)
            except Exception as exc:
                self.errors.append(SourceError(entry.page.path, str(exc)))

    def apply_options(self, options: Options) -> None:
        """Adopt new settings, re-detecting only if detection depends on them."""
        needs_redetect = (
            options.pad != self.options.pad
            or options.full_ink != self.options.full_ink
        )
        self.options = options
        if needs_redetect:
            self.redetect()

    # -- what it would produce ----------------------------------------------

    def blocks(self) -> list[Block]:
        return [b for b in (e.as_block() for e in self.entries) if b is not None]

    def packing(self, options: Options | None = None) -> PackResult | None:
        blocks = self.blocks()
        if not blocks:
            return None
        return pack(blocks, options or self.options)

    def estimate(self) -> Estimate:
        """The live sheet count, and what minimising pages would be worth.

        The GUI shows the trade before the user commits to it, so ticking
        "minimise pages" is an informed choice rather than a guess.
        """
        blocks = self.blocks()
        if not blocks:
            return Estimate()

        result = pack(blocks, self.options)
        estimate = Estimate(
            blocks=len(blocks),
            sheets=result.sheet_count,
            saved=max(len(blocks) - result.sheet_count, 0),
            reorder_saved=result.reorder_saved,
        )
        if not self.options.reorder:
            from dataclasses import replace

            alternative = pack(blocks, replace(self.options, reorder=True))
            estimate.reorder_would_save = max(
                result.sheet_count - alternative.sheet_count, 0
            )
        return estimate

    def command_line(self, output: Path | None = None) -> str:
        """The equivalent `eco-print` invocation (UC-08).

        Lets a user build a configuration by eye and then automate it. Manual
        crops cannot be expressed as flags, so they are flagged as the one thing
        the command line will not reproduce.
        """
        parts = ["eco-print"]
        parts += [_quote(str(path)) for path in _distinct_paths(self.entries)]
        if output:
            parts.append(_quote(str(output)))
        parts += self.options.to_cli_args()
        line = " ".join(parts)
        if any(entry.is_manual for entry in self.entries):
            line += "    # note: manual crops are not reproduced by these flags"
        return line


def _distinct_paths(entries: list[Entry]) -> list[Path]:
    """Each source document once, in list order."""
    seen: set[Path] = set()
    ordered: list[Path] = []
    for entry in entries:
        if entry.page.path not in seen:
            seen.add(entry.page.path)
            ordered.append(entry.page.path)
    return ordered


def _quote(value: str) -> str:
    return f"'{value}'" if " " in value else value

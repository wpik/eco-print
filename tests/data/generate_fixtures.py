#!/usr/bin/env python3
"""Generate the synthetic PDF fixtures used by the test suite.

Dependency-free: writes minimal but valid PDFs directly, so the corpus can be
regenerated on any machine without installing anything.

Each fixture pins its ink extent exactly by drawing a hairline rule at the top
and bottom of every intended content band. Tests can therefore assert detected
heights against numbers this generator chose, rather than against whatever a
text renderer happened to produce.

Run:  python tests/data/generate_fixtures.py [OUTPUT_DIR]

Regeneration is deterministic, and a test asserts that re-running it leaves the
committed fixtures byte-identical, so the corpus cannot drift from the
description in docs/README.md. The single exception is `encrypted.pdf`, whose
bytes are pypdf's business.
"""
from pathlib import Path

A4 = (595.275, 841.889)
A4_LANDSCAPE = (841.889, 595.275)

HERE = Path(__file__).parent


class Page:
    """A page described in top-down coordinates, in points."""

    def __init__(self, size=A4):
        self.size = size
        self.ops = []

    def rule(self, top, x0=56, x1=None, thickness=1.0):
        """Horizontal rule whose TOP edge sits `top` points below the page top."""
        w, h = self.size
        x1 = w - 56 if x1 is None else x1
        self.ops.append(f"0 0 0 rg {x0:.2f} {h - top - thickness:.2f} "
                        f"{x1 - x0:.2f} {thickness:.2f} re f")
        return self

    def text(self, top, s, size=11, x=56):
        """Text whose approximate cap-height top sits `top` points below the top."""
        w, h = self.size
        esc = s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        self.ops.append(f"BT /F1 {size} Tf {x:.2f} {h - top - size:.2f} Td ({esc}) Tj ET")
        return self

    def band(self, top, height, title, lines=3):
        """A content band with rules pinning its exact ink extent."""
        self.rule(top, thickness=1.5)
        self.text(top + 14, title, size=13)
        step = max(16.0, (height - 44) / max(lines, 1))
        for i in range(lines):
            y = top + 40 + i * step
            if y > top + height - 14:
                break
            self.text(y, f"Line {i + 1} of {title} - sample content for layout tests.", size=9)
        self.rule(top + height - 1.0, thickness=1.0)
        return self

    def stream(self):
        return "\n".join(self.ops).encode("latin-1")


def write_pdf(path: Path, pages):
    """Assemble pages into a PDF with a correct xref table."""
    objects = {}          # number -> bytes body
    n_pages = len(pages)
    font_no = 2 + 2 * n_pages + 1

    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = f"<< /Type /Pages /Count {n_pages} /Kids [ {kids} ] >>".encode()

    for i, page in enumerate(pages):
        page_no = 3 + 2 * i
        content_no = page_no + 1
        w, h = page.size
        objects[page_no] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [ 0 0 {w:.3f} {h:.3f} ] "
            f"/Resources << /Font << /F1 {font_no} 0 R >> >> "
            f"/Contents {content_no} 0 R >>"
        ).encode()
        data = page.stream()
        objects[content_no] = (
            f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"
        )

    objects[font_no] = (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                        b"/Encoding /WinAnsiEncoding >>")

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"

    xref_at = len(out)
    size = max(objects) + 1
    out += f"xref\n0 {size}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, size):
        out += (f"{offsets[num]:010d} 00000 n \n".encode() if num in offsets
                else b"0000000000 65535 f \n")
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()

    path.write_bytes(bytes(out))
    return path


# --- the corpus -----------------------------------------------------------
# Heights are the intended ink extents; detection should report them plus the
# padding it adds on each side.

TOP = 40.0   # every band starts 40pt below the page top


def build(out_dir: Path | None = None):
    """Write the whole corpus into `out_dir` (default: next to this script)."""
    out = HERE if out_dir is None else out_dir
    out.mkdir(parents=True, exist_ok=True)
    made = []

    # A batch of five ordinary documents of differing heights. Packed in order
    # with the default settings these occupy two sheets, 3 + 2.
    batch = [("a", 150.0), ("b", 230.0), ("c", 300.0), ("d", 180.0), ("e", 260.0)]
    for name, height in batch:
        p = Page()
        p.band(TOP, height, f"Statement {name.upper()}", lines=6)
        made.append(write_pdf(out / f"statement-{name}.pdf", [p]))

    # Three documents that expose the difference between ordered and reordered
    # packing: in order they need three sheets, reordered only two.
    for name, height in [("a", 390.0), ("b", 500.0), ("c", 340.0)]:
        p = Page()
        p.band(TOP, height, f"Packing case {name.upper()}", lines=8)
        made.append(write_pdf(out / f"packing-{name}.pdf", [p]))

    # Content band, a large gap, then a trailing footer: the largest-gap rule
    # should drop the footer.
    p = Page()
    p.band(TOP, 200.0, "Notice with footer", lines=4)
    p.rule(760.0, thickness=0.5)
    p.text(768.0, "Small print that should not be printed with the content.", size=7)
    made.append(write_pdf(out / "with-footer.pdf", [p]))

    # Two genuine content blocks split by a large gap: the safety condition must
    # refuse the cut and keep both.
    p = Page()
    p.band(TOP, 260.0, "Upper block", lines=6)
    p.band(520.0, 260.0, "Lower block", lines=6)
    made.append(write_pdf(out / "two-blocks.pdf", [p]))

    # A page of solid text: no structural gap, so nothing may be dropped.
    p = Page()
    p.band(TOP, 760.0, "Dense report", lines=40)
    made.append(write_pdf(out / "full-page.pdf", [p]))

    # No ink at all.
    made.append(write_pdf(out / "blank.pdf", [Page()]))

    # Landscape.
    p = Page(A4_LANDSCAPE)
    p.band(TOP, 180.0, "Landscape sheet", lines=4)
    made.append(write_pdf(out / "landscape.pdf", [p]))

    # Three pages of differing heights in one document.
    pages = []
    for name, height in [("one", 120.0), ("two", 300.0), ("three", 200.0)]:
        p = Page()
        p.band(TOP, height, f"Bundle page {name}", lines=5)
        pages.append(p)
    made.append(write_pdf(out / "multipage.pdf", pages))

    # Taller than the usable area of a sheet: must land alone and be reported.
    p = Page()
    p.band(10.0, 825.0, "Oversized block", lines=40)
    made.append(write_pdf(out / "oversized.pdf", [p]))

    made.extend(build_encrypted(out))
    return made


def build_encrypted(out: Path | None = None):
    """An encrypted fixture: owner password set, user password empty.

    Needs pypdf, which is a project dependency but not needed to regenerate the
    rest of the corpus. Skipped with a note if it is missing; the committed
    fixture stays valid either way.
    """
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        print("  (skipping encrypted.pdf - pypdf not installed)")
        return []
    out = HERE if out is None else out
    src = out / "statement-b.pdf"
    writer = PdfWriter()
    writer.append(PdfReader(str(src)))
    writer.encrypt(user_password="", owner_password="eco-print-fixture")
    target = out / "encrypted.pdf"
    with open(target, "wb") as fh:
        writer.write(fh)
    return [target]


if __name__ == "__main__":
    import sys

    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    for path in build(destination):
        print(f"  {path.name:24s} {path.stat().st_size:6d} bytes")

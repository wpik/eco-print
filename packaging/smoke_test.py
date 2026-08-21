#!/usr/bin/env python3
"""Post-build check that the packaged executable actually works (UC-09).

Run after `pyinstaller eco-print.spec`, from the `packaging/` directory:

    python smoke_test.py

Exercises the built binary exactly the way a user would -- not by importing
eco_print in-process, which would prove nothing about the packaging step
itself -- against the same statement-*.pdf fixtures used throughout the test
suite, and checks the documented 5-into-2-pages result. A packaging mistake
(a missing Qt plugin, a hidden import PyInstaller's static analysis missed,
a broken relative import) fails a real subprocess run, not a mock.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

PACKAGING_DIR = Path(__file__).parent
REPO_ROOT = PACKAGING_DIR.parent
FIXTURES = REPO_ROOT / "tests" / "data"
EXPECTED_PAGES = 2


def find_binary() -> Path:
    """Where PyInstaller put the built executable, per platform."""
    dist = PACKAGING_DIR / "dist"
    if sys.platform == "darwin":
        candidate = dist / "eco-print.app" / "Contents" / "MacOS" / "eco-print"
    elif sys.platform == "win32":
        candidate = dist / "eco-print" / "eco-print.exe"
    else:
        candidate = dist / "eco-print" / "eco-print"
    if not candidate.is_file():
        sys.exit(f"smoke test: built binary not found at {candidate}")
    return candidate


def run(binary: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(binary), *args], capture_output=True, text=True, timeout=60
    )


def main() -> int:
    binary = find_binary()
    print(f"smoke test: using {binary}")

    version = run(binary, "--version")
    if version.returncode != 0:
        print(f"FAIL: --version exited {version.returncode}\n{version.stderr}")
        return 1
    print(f"  --version -> {version.stdout.strip()}")

    statements = sorted(FIXTURES.glob("statement-*.pdf"))
    if len(statements) != 5:
        sys.exit(f"smoke test: expected 5 statement-*.pdf fixtures, found {len(statements)}")

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "combined.pdf"
        merge = run(binary, *[str(p) for p in statements], str(output))
        if merge.returncode != 0:
            print(f"FAIL: merge exited {merge.returncode}\n{merge.stderr}")
            return 1
        print(f"  merge -> {merge.stdout.strip()}")

        if not output.exists():
            print("FAIL: no output file was written")
            return 1

        from pypdf import PdfReader

        pages = len(PdfReader(str(output)).pages)
        if pages != EXPECTED_PAGES:
            print(f"FAIL: expected {EXPECTED_PAGES} pages, got {pages}")
            return 1
        print(f"  output has {pages} pages, as expected")

    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The graphical front end (UC-03, UC-04, UC-08).

Qt is an optional dependency: `pip install eco-print` gives a working command
line, and only `pip install 'eco-print[gui]'` pulls in PySide6. Nothing outside
this package imports Qt, so the core stays testable without a display.
"""
from __future__ import annotations


def launch(paths: list[str] | None = None) -> int:
    """Start the GUI, optionally pre-loaded with paths. Returns an exit code."""
    try:
        from .app import run_app
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise MissingGui(
            "the graphical interface needs PySide6; install it with:\n"
            "    pip install 'eco-print[gui]'"
        ) from exc
    return run_app(paths or [])


class MissingGui(Exception):
    """PySide6 is not installed. Carries the sentence shown to the user."""

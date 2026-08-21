"""The script PyInstaller builds from.

`eco_print.cli:main` is a package-relative module and cannot be pointed at
directly -- PyInstaller (like any script runner) needs a top-level script
whose imports resolve normally, so this thin wrapper is that script. It has
no logic of its own beyond handing off to the real entry point (UC-09).
"""
from eco_print.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

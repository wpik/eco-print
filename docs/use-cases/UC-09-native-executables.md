# UC-09 — Package as a native executable

**Actor:** a user who does not have Python, and does not want to install it,
on Windows, macOS or Linux.
**Goal:** download one file, run it, and get the same tool the CLI and
`pip install` give a Python user — no venv, no `pip`.

## Why this exists

Everything documented elsewhere in `docs/` assumes a Python environment:
`pip install`, a venv, `eco-print` on the `PATH`. That is the right default
for developers and for CI, but it is a real barrier for someone who only
wants to compact a few PDFs before printing them. A native executable removes
that barrier entirely.

## What gets built

**One artifact per platform, each a dual-mode binary** — the same `eco-print`
entry point the rest of this project uses, unmodified: no arguments opens the
GUI ([UC-03](UC-03-gui-select-and-drop.md)), any arguments run the CLI
([UC-01](UC-01-cli-merge-explicit-files.md)). There is no separate "GUI build"
and "CLI build" to keep in sync — packaging one entry point is what keeps
that guarantee true for free.

| Platform | What ships | Launch as CLI | Launch as GUI |
| --- | --- | --- | --- |
| macOS | `eco-print.app` | run the binary inside `Contents/MacOS/` from Terminal | double-click, or open the `.app` |
| Windows | `eco-print.exe` (+ its supporting folder) | run from `cmd.exe`/PowerShell | double-click, or Start menu |
| Linux | `eco-print` binary (+ its supporting folder) | run from a terminal | run from a file manager or launcher |

## The Windows console problem, and how it is handled

A GUI application on Windows is normally built as a **windowed** binary: no
console window ever appears, which is correct for double-click launches, but
means the process has **no connection at all** to a console it was started
from — printed output silently disappears even though the underlying logic
ran correctly. macOS and Linux have no equivalent problem: a windowed binary
there behaves identically whether launched from a terminal or a file manager.

The fix is a few lines in `cli.py`, run as the very first thing `main()`
does, gated to `sys.platform == "win32"`: call the Windows API's
`AttachConsole(-1)`, which joins the console of whatever process launched
this one, if any. When the exe was double-clicked, there is no such console
and the call harmlessly fails, leaving the app to run as pure GUI. When the
exe was run from `cmd.exe` or PowerShell, it attaches to that console and
`stdout`/`stderr` are reopened against it, so CLI output appears exactly as
it would from a normal console build. A plain console-subsystem build (or
any non-Windows platform) never reaches this code path at all.

The alternative — always building with a console window on Windows — was
considered and rejected: it would mean a black console window flashing (or
staying open) every time a user double-clicks the GUI, which the other two
platforms never do.

## Build tooling

**PyInstaller**, not Briefcase. Briefcase was tried first and found
unsuitable: its packaging model is built around per-GUI-framework app
templates, the official one targets BeeWare's own Toga toolkit, and no
maintained community template exists for PySide6 — confirmed by generating a
scratch project with it and finding it silently produced a Toga app even
when a PySide6 framework was requested, and by searching GitHub for a
community template and finding none actively maintained. Making Briefcase
work would mean writing a packaging template from scratch, not configuring
an existing one.

One `packaging/eco-print.spec` file describes the build for all three
platforms; **PyInstaller does not cross-compile**, so each platform still
runs its own `pyinstaller` invocation, but they run from identical
instructions rather than three drifting configs.

### Keeping the artifact small

PySide6 ships far more than this project uses — WebEngine (an embedded
Chromium build), Qml/Quick, Multimedia, 3D, the mobile/sensor modules, and
more. A naive `--collect-all PySide6` build, tried first, produced a
663&nbsp;MB `.app` for a tool that only imports `QtCore`, `QtGui` and
`QtWidgets` (verified by grepping `src/` for every `PySide6` import). The
spec file excludes every unused Qt submodule explicitly; the same build with
those exclusions came to 127&nbsp;MB — a fifth of the size, with no change in
behaviour, verified by re-running the same checks against it.

## Continuous integration

`.github/workflows/build.yml` builds all three platforms in a matrix
(`macos-latest`, `windows-latest`, `ubuntu-latest`), triggered by a version
tag (`v*`) or manually (`workflow_dispatch`). Each job builds from the spec,
then runs `packaging/smoke_test.py` against the **real built binary** — not
an in-process import, which would prove nothing about packaging — exercising
`--version` and the same five-statement merge documented throughout this
project, asserting the built executable produces the documented 2-page
result before the artifact is uploaded. A packaging mistake (a missing Qt
plugin, a hidden import PyInstaller's static analysis missed, a broken
relative import) fails CI with a real subprocess run, not a mock.

Builds are **unsigned**. Users see a one-time "unknown developer" warning on
first launch on macOS and Windows, which they click through. Code signing
needs a paid Apple Developer account and a Windows code-signing certificate —
real costs and account setup outside what can be done without the user's own
credentials — and is deliberately out of scope for now.

## Rules

- The spec file is the single source of truth for what gets bundled; CI does
  not duplicate its logic, only invokes it.
- Nothing about the packaged build changes the application's behaviour or
  its tests — `packaging/entrypoint.py` is a bare two-line wrapper handing off
  to `eco_print.cli.main`, the same function the pip-installed console script
  calls.
- The console-attach code has no effect on any non-Windows platform, and no
  effect on an ordinary (non-frozen, or console-subsystem) Windows run: it is
  only reachable at all when `sys.platform == "win32"`, and `AttachConsole`
  is a no-op failure in every situation except "a windowed binary was
  launched from an existing console."

## Acceptance criteria

- A build on each platform produces one artifact that launches the GUI with
  no arguments and behaves as the documented CLI with arguments.
- CI's smoke test — run against the actual built binary, not the Python
  source — passes on all three platforms before an artifact is uploaded.
- The macOS/Linux artifact size stays a small fraction of a naive
  `--collect-all PySide6` build; the excluded-modules list in the spec file
  is the reason, not an incidental result.
- Running the Windows build from `cmd.exe` with file arguments prints the
  same summary line the other two platforms do; double-clicking it opens the
  GUI with no console window.

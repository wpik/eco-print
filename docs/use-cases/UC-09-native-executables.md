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
does, gated to `sys.platform == "win32"`. It checks **`GetStdHandle`**
before doing anything else, rather than reaching straight for
`AttachConsole` — the two tell apart cases that need different handling:

* **A real stdout handle already exists.** This covers running from an
  existing console with handles inherited (the ordinary cmd.exe/PowerShell
  case), and, separately, being driven *programmatically* by another process
  through a redirected pipe — exactly what `packaging/smoke_test.py` does to
  the built exe. Python's own `sys.stdout` is still `None` here regardless
  (PyInstaller's windowed bootloader leaves it that way no matter what the
  OS-level handle is), so it is rebound directly to the handle that already
  exists.
* **No handle exists at all**: a genuine double-click launch, or a process
  tree that did not inherit handles. Only here does `AttachConsole(-1)` run,
  joining the console *session* of whatever launched this process, if any —
  a harmless no-op failure when there is none.

Getting this backwards — calling `AttachConsole` unconditionally, which is
what shipped first — silently breaks the second case: `AttachConsole` joins
the process's console *session*, which is a different thing from a
redirected *handle*, so it steals output away to whatever session the
process happens to have inherited even when a caller was reading a
redirected pipe. This was found by CI itself: the smoke test's own captured
`--version` and merge-summary text came back **empty** on the Windows build,
even though the underlying merge worked and produced the correct 2-page
file — the exe's `print()` calls were succeeding, just not into the pipe the
smoke test was reading. `packaging/smoke_test.py` is exactly the
programmatic-caller case the fix now handles, so it doubles as this
behaviour's regression test: if it silently starts capturing empty output on
Windows again, CI catches it printing nothing rather than declaring success.

The alternative to any of this — always building with a console window on
Windows — was considered and rejected: it would mean a black console window
flashing (or staying open) every time a user double-clicks the GUI, which
the other two platforms never do.

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
`QtWidgets` (verified by grepping `src/` for every `PySide6` import).
Excluding every unused top-level Qt submodule brought the same build to
127&nbsp;MB.

That exclusion list only stops modules PyInstaller reaches by walking Python
imports, though — it does not stop a second, separate mechanism: Qt's own
plugin directories (`platforminputcontexts/`, `tls/`, ...) are bundled
wholesale by category, and one plugin needing an extra Qt module is enough to
drag that whole module back in regardless of the exclusion list. This is how
QtQml, QtQuick, QtVirtualKeyboard, QtNetwork, QtOpenGL, QtSvg and QtPdf all
survived the first pass despite being explicitly excluded — none of them are
used, but a virtual (on-screen) keyboard input plugin, three TLS backend
plugins, an SVG icon plugin and a "render a PDF as an image" plugin, none of
which this desktop app with no network access and no on-screen keyboard has
any use for, each pulled one back in.

The fix filters `Analysis`'s output directly, after it runs, rather than
trying to prevent the pull-in in the first place. **One exclusion in that
list was wrong and is documented as a mistake, not silently corrected**:
`QtDBus` looked like the same kind of unused weight, but `otool -L` on
`QtGui.framework` shows it is a hard, load-time dependency of `QtGui` itself
on macOS — not something only an optional plugin reaches for. Excluding it
made `import PySide6.QtGui` fail outright, caught by actually launching the
built GUI rather than trusting the exclusion list on paper; the fix was to
verify each candidate individually with `otool -L` before removing it, not
to assume "unused Qt module" always means "safe to strip." With that
correction, the build came to 103&nbsp;MB.

Every step of this was verified against a real build, not assumed: `otool -L`
confirmed what actually links what, the smoke test's real merge still
produces the documented 2-page result at each stage, and a full GUI exercise
(loading a real document, painting the crop view, toggling settings) was run
against a reproduction of the final exclusion set before it was trusted.

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

### The macOS artifact is not just the .app, twice

The first CI run produced a macOS artifact of 327&nbsp;MB against a 103&nbsp;MB
`.app` — a gap too large to be the exclusion list's doing, found by
downloading the actual artifact and measuring what was in it rather than
guessing. Two separate causes, both fixed in the upload step rather than the
build itself:

- PyInstaller's macOS bundle uses symlinks between `Contents/Frameworks` and
  `Contents/Resources` so the same libraries are not stored twice on disk;
  `actions/upload-artifact`'s own zip step does not preserve symlinks, and
  was found to materialize each one as a full real copy — doubling the
  bundle's size on its own. The fix is to archive the `.app` with `ditto`
  (Apple's own tool for this, which does preserve them) before handing a
  single file to `upload-artifact`, rather than pointing it at the bundle
  directory.
- `dist/` holds both the finished `eco-print.app` and the loose
  `dist/eco-print/` onedir folder BUNDLE was built from — intermediate
  output, not something to ship. The workflow previously uploaded
  `packaging/dist/*`, which grabbed both; it now archives each platform to
  exactly **one file** (`ditto` on macOS as above, `Compress-Archive` on
  Windows, `tar -czf` on Linux — chosen there over zip because it reliably
  preserves the executable bit, verified by extracting a `tar`-built archive
  and confirming `eco-print` came out `-rwxr-xr-x` without a manual `chmod`)
  and uploads only that.

### Release assets

On a tag push (`if: startsWith(github.ref, 'refs/tags/')`), a `release` job
runs after the three builds complete, downloads their three single-file
archives, and attaches them to the GitHub Release for that tag with
`gh release upload` — or `gh release create --generate-notes` first, if
pushing the tag did not already create one. Either way this is idempotent:
re-running the workflow against the same tag (`--clobber` on the upload)
replaces the assets rather than failing on "already exists," which matters
for fixing a bad build without needing a new tag.

This only runs for a real tag push. `workflow_dispatch` runs (used throughout
this project's own development to test changes before cutting a release) are
never against a tag, so `startsWith(github.ref, 'refs/tags/')` is false and
the release job — along with any assumption that a release exists to attach
to — is skipped entirely; only the plain workflow artifacts are produced, as
before.

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
- Running the Windows build as a subprocess with its output captured (as
  `packaging/smoke_test.py` does) also produces real text, not an empty
  string -- the distinct case `GetStdHandle` exists to tell apart from a
  console launch.
- Every module removed from the build is verified with `otool -L` (or the
  platform equivalent) to confirm nothing load-bearing actually depends on
  it, not assumed safe because it looked unused -- `QtDBus` is the concrete
  example of why this matters.
- The downloaded macOS CI artifact is close to the size of the `.app` it
  contains -- not roughly double it from a duplicated onedir folder, and not
  further inflated by symlinks-turned-real-copies.
- Pushing a version tag results in all three platform archives attached to
  that tag's GitHub Release as downloadable assets, without a person having
  to visit the Actions tab and download a workflow artifact by hand.
- Re-running the workflow against the same tag (a fixed build after a bad
  one) replaces the existing release assets rather than failing.
- A `workflow_dispatch` run against a branch never touches the release
  step -- only a real tag push does.

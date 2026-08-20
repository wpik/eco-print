# UC-08 — Every option available in both front ends

**Actor:** a user who has learned the tool in one front end and moved to the other.
**Goal:** anything that can be asked of the CLI can be asked of the GUI, and vice
versa. Neither mode is a reduced version of the other.

## The requirement

Every setting that changes the *content of the output* must be reachable from
both the command line and the GUI. A user must never have to drop to a terminal
to get a result the GUI cannot produce.

## Single source of truth

Parity by discipline fails the first time a flag is added. Instead the options
are declared **once**, in `eco_print/settings.py`, as a dataclass whose fields
carry their own metadata: flag name, type, default, range, help text, and the
kind of GUI control that represents them.

    Options
      ├── argparse parser  (generated from the fields)
      └── GUI settings panel  (generated from the same fields)

Adding an option therefore means editing one file, and it appears in both places
at once. A test walks the dataclass and asserts that every field is reachable
from both front ends, so a field that somehow gains a CLI flag but no GUI control
fails the suite rather than shipping.

## The mapping

| Option | CLI | GUI control |
| --- | --- | --- |
| Outer sheet margin | `--margin PT` | Spin box, points, in the settings panel |
| Minimum gap between blocks | `--gap PT` | Spin box, points |
| Padding kept around detected content | `--pad PT` | Spin box, points |
| Output sheet size | `--page-size` | Drop-down (A4, Letter, …) |
| Keep all ink, drop nothing | `--full-ink` | Check box, "keep footers and page numbers" |
| Separator rule between blocks | `--separator` | Check box, "rule between documents" |
| Give up order for fewest sheets | `--reorder` | Check box, "minimise pages (ignore order)" |
| Recursive directory scan | `--recursive` | Check box on the folder-drop prompt, and in the panel |
| Detail about what was detected and dropped | `-v/--verbose` | "Details" panel, expandable, showing the same per-page report |

### Options whose GUI form is behaviour, not a control

Three CLI flags exist only because a terminal cannot do what a window does. They
are satisfied in the GUI, but by its nature rather than by a widget — and this is
the whole list, so nothing is quietly missing:

| Option | CLI | Why the GUI needs no control |
| --- | --- | --- |
| Overwrite an existing output | `--force` | The native save dialog already asks before replacing a file, which is the same protection the flag exists to bypass. |
| Report without writing | `--dry-run` | The GUI is a live dry run: the status line shows the sheet count continuously, and nothing is written until `Save PDF`. |
| Choose the output path | trailing argument | The output field and `Browse` button. |

## Live effect

Every control in the settings panel re-runs the affected part of the pipeline
immediately:

- `--pad` and `--full-ink` change **detection**, so pages with automatic boxes
  are re-detected. Pages the user cropped by hand ([UC-04](UC-04-gui-manual-crop.md))
  keep their manual boxes and are left alone.
- `--margin`, `--gap`, `--page-size` and `--reorder` change **packing** only, so
  the sheet count updates without re-rendering anything.
- The status line reflects the new result at once, which turns the settings panel
  into a way of *seeing* how each option affects paper use rather than guessing.

## Persistence and transfer

- Settings persist between GUI sessions, so a user with a habitual margin sets it
  once. Inputs and crops are not persisted; only settings are.
- `Reset to defaults` restores every field to the documented default.
- *(Optional, cheap, worth having)* **Copy as command line** puts the equivalent
  `eco-print …` invocation on the clipboard, with the current settings as flags.
  It lets a user build a configuration by eye and then automate it, and it makes
  the parity in this document visible rather than merely claimed.

## Acceptance criteria

- Every field of `Options` is reachable from the CLI parser and from the GUI
  settings panel; the parity test enumerates the dataclass and fails on any gap.
- The three behaviour-satisfied flags above are the only exceptions, and the test
  asserts that this exception list is exactly that long — a new flag cannot be
  quietly added to it.
- The same inputs and the same settings produce identical output from both front
  ends, byte for byte.
- Changing any packing setting in the GUI updates the sheet count without
  re-running detection.
- `Copy as command line`, when implemented, produces an invocation that actually
  reproduces the GUI's current result.

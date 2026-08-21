# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for eco-print (UC-09).

One spec covers all three platforms: PyInstaller does not cross-compile, so
the actual build still runs once per OS (see .github/workflows/build.yml),
but the same instructions apply everywhere rather than maintaining three
near-duplicate specs.

Only PySide6.QtCore, QtGui and QtWidgets are used by this project (verified
by grepping src/ for PySide6 imports) -- everything else PySide6 ships
(WebEngine, Qml/Quick, Multimedia, 3D, the mobile/sensor modules...) is
excluded. Without this, a naive --collect-all PySide6 build bundles Qt's
entire Chromium-based WebEngine and pulls the artifact well past 600MB for
a tool that never opens a browser view.
"""
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# pypdfium2 ships a compiled PDFium binary as package data; pypdf's own
# metadata/version probing needs its full package present too. Both were
# silently missing at runtime without this (found by actually running a
# built binary, not assumed).
pdfium_datas, pdfium_binaries, pdfium_hidden = collect_all("pypdfium2")
pypdf_datas, pypdf_binaries, pypdf_hidden = collect_all("pypdf")

EXCLUDED_QT_MODULES = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtTest",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtRemoteObjects",
    "PySide6.QtWebSockets",
    "PySide6.QtWebChannel",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech",
    "PySide6.QtLocation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
]

a = Analysis(
    ["entrypoint.py"],
    pathex=[],
    binaries=pdfium_binaries + pypdf_binaries,
    datas=pdfium_datas + pypdf_datas,
    hiddenimports=pdfium_hidden + pypdf_hidden,
    hookspath=[],
    excludes=EXCLUDED_QT_MODULES,
    noarchive=False,
)

# `excludes` above only stops modules PyInstaller reaches by walking Python
# imports. Several Qt binaries get pulled in a second way entirely: Qt's own
# plugin directories (styles/, platforminputcontexts/, tls/, ...) are
# bundled wholesale per category, and one plugin needing an extra Qt module
# is enough to drag that whole module -- and everything IT needs -- in too,
# regardless of `excludes`.
#
# Verified with `otool -L` before removing any of these, rather than
# assumed: none of QtCore, QtGui, QtWidgets, or the macOS Cocoa platform
# plugin itself (the one thing genuinely load-bearing) link any of them.
# What actually pulls each one in:
#   - platforminputcontexts/libqtvirtualkeyboardplugin.dylib (an on-screen
#     keyboard for touch input, irrelevant to a desktop app) drags in
#     QtVirtualKeyboard, QtQml, QtQuick and, through them, QtNetwork and
#     QtOpenGL -- the single biggest chunk of unnecessary weight.
#   - tls/lib*backend.dylib, generic/libqtuiotouchplugin.dylib and
#     networkinformation/libqapplenetworkinformation.dylib each need
#     QtNetwork; the app makes no network requests at all.
#   - iconengines/libqsvgicon.dylib and imageformats/libqsvg.dylib need
#     QtSvg; nothing in src/ uses a QIcon or loads an SVG.
#   - imageformats/libqpdf.dylib needs QtPdf, Qt's own PDF renderer --
#     unused, pypdfium2 renders every page in this project.
#
# QtDBus is deliberately NOT in this list, despite looking like the same
# kind of unused weight: unlike everything above, it is a hard, load-time
# dependency of QtGui.framework itself on macOS (confirmed with
# `otool -L QtGui.framework/.../QtGui`, which lists QtDBus.framework
# directly) rather than something only an optional plugin reaches for.
# Removing it does not just drop a feature -- it makes `import PySide6.QtGui`
# fail outright, which is exactly what happened the first time this list
# included it: the GUI stopped launching, caught by actually running the
# packaged binary rather than trusting the exclusion list on paper.
EXCLUDED_BINARY_PATTERNS = (
    "platforminputcontexts",
    "libqtvirtualkeyboardplugin",
    "QtVirtualKeyboard",
    "QtQml",
    "QtQuick",
    "tls",
    "networkinformation",
    "libqtuiotouchplugin",
    "QtNetwork",
    "QtOpenGL",
    "libqsvg",
    "QtSvg",
    "libqpdf",
    "QtPdf",
)


def _is_excluded_binary(dest_path: str) -> bool:
    return any(pattern in dest_path for pattern in EXCLUDED_BINARY_PATTERNS)


a.binaries = [entry for entry in a.binaries if not _is_excluded_binary(entry[0])]
a.datas = [entry for entry in a.datas if not _is_excluded_binary(entry[0])]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="eco-print",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="eco-print",
)

app = BUNDLE(
    coll,
    name="eco-print.app",
    icon=None,
    bundle_identifier="com.wpik.eco-print",
)

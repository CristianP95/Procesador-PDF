# -*- mode: python ; coding: utf-8 -*-
# Uso: pyinstaller --noconfirm --clean PDFTaller.spec
excluir = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
    "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtSql",
    "tkinter", "pytest", "pymupdf4llm", "pymupdf_layout", "networkx",
]

a = Analysis(
    ["lanzador.py"],
    pathex=["src"],
    hiddenimports=[],
    excludes=excluir,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="PDFTaller",
    console=False,          # sin ventana negra de CMD
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PDFTaller", upx=False)

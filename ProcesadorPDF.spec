# -*- mode: python ; coding: utf-8 -*-
# Uso: pyinstaller --noconfirm --clean ProcesadorPDF.spec
excluir = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
    "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtSql",
    "tkinter", "pytest", "pymupdf4llm", "pymupdf_layout", "networkx",
]

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# Datos de OCR (Tesseract): construir_exe.bat los descarga en .\tessdata
datas = [("tessdata", "tessdata")] if os.path.isdir("tessdata") else []
datas += collect_data_files("pyhanko")
# Versiones de los componentes que muestra "Acerca de"
for dist in ("pymupdf", "PySide6", "pyhanko", "cryptography"):
    datas += copy_metadata(dist)
# Logo, icono e historial de versiones (ventana "Acerca de")
datas += [("src/procesador_pdf/gui/assets", "procesador_pdf/gui/assets"), ("CHANGELOG.md", "procesador_pdf/gui/assets")]

a = Analysis(
    ["lanzador.py"],
    pathex=["src"],
    datas=datas,
    hiddenimports=collect_submodules("pyhanko") + collect_submodules("pyhanko_certvalidator"),
    excludes=excluir,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ProcesadorPDF",
    console=False,          # sin ventana negra de CMD
    icon="src/procesador_pdf/gui/assets/app.ico",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ProcesadorPDF", upx=False)

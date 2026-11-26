"""Identidad de la aplicación: nombre, autor, enlaces y logo.

Cambiar el nombre de la aplicación solo requiere editar este archivo
(y el nombre del ejecutable en el archivo .spec).
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import __version__

APP_NAME = "Procesador PDF"
APP_ID = "ProcesadorPDF"                      # nombre sin espacios (ejecutable, carpetas)
DESCRIPTION = ("Herramienta de código abierto para ordenar, optimizar, convertir, editar "
               "y proteger documentos PDF.")
AUTHOR = "Cristian Pineda"
ORGANIZATION = "CP"
LICENSE = "AGPL-3.0"
REPOSITORY = "https://github.com/CristianP95/Procesador-PDF"
VERSION = __version__


def asset(name: str) -> Path:
    """Ruta de un recurso del paquete (funciona también en el ejecutable de PyInstaller)."""
    base = Path(getattr(sys, "_MEIPASS", "")) / "procesador_pdf" / "gui" / "assets"
    if base.is_dir():
        return base / name
    return Path(__file__).parent / "gui" / "assets" / name


def changelog() -> str:
    """Historial de versiones (CHANGELOG.md de la raíz del proyecto, incluido en el ejecutable)."""
    for p in (asset("CHANGELOG.md"), Path(__file__).resolve().parents[2] / "CHANGELOG.md"):
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""

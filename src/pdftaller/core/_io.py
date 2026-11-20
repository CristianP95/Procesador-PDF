"""Utilidades internas para abrir y guardar documentos."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Union

import pymupdf

from .errors import PasswordError, PdfTallerError

PathLike = Union[str, os.PathLike]


def open_pdf(path: PathLike, password: str | None = None) -> pymupdf.Document:
    """Abre un PDF; si está cifrado intenta autenticarse con ``password``."""
    try:
        # Se lee en memoria para no bloquear el archivo (en Windows) y poder sobrescribirlo.
        doc = pymupdf.open(stream=Path(path).read_bytes(), filetype="pdf")
    except Exception as exc:  # pymupdf lanza varios tipos
        raise PdfTallerError(f"No se pudo abrir '{path}': {exc}") from exc
    if not doc.is_pdf:
        doc.close()
        raise PdfTallerError(f"'{path}' no es un PDF")
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            doc.close()
            raise PasswordError(f"'{path}' está protegido: contraseña incorrecta o ausente")
    return doc


def save_pdf(doc: pymupdf.Document, output: PathLike, **kwargs) -> Path:
    """Guarda ``doc`` de forma atómica (archivo temporal + reemplazo).

    Por defecto conserva el cifrado que tuviera el documento original.
    """
    kwargs.setdefault("encryption", pymupdf.PDF_ENCRYPT_KEEP)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    try:
        doc.save(tmp, garbage=3, deflate=True, **kwargs)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out

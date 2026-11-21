"""Utilidades internas para abrir y guardar documentos."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Union

import pymupdf

from .errors import PasswordError, PdfTallerError

PathLike = Union[str, os.PathLike]


def open_pdf(path: PathLike, password: str | None = None, *, for_edit: bool = True) -> pymupdf.Document:
    """Abre un PDF; si está cifrado intenta autenticarse con ``password``.

    Con ``for_edit=True`` respeta las restricciones del documento: si no permite modificarlo y no
    se dio la contraseña de propietario, lanza ``PasswordError``.
    """
    try:
        # Se lee en memoria para no bloquear el archivo (en Windows) y poder sobrescribirlo.
        doc = pymupdf.open(stream=Path(path).read_bytes(), filetype="pdf")
    except Exception as exc:  # pymupdf lanza varios tipos
        raise PdfTallerError(f"No se pudo abrir '{path}': {exc}") from exc
    if not doc.is_pdf:
        doc.close()
        raise PdfTallerError(f"'{path}' no es un PDF")
    auth = 0
    if doc.needs_pass:
        auth = doc.authenticate(password) if password else 0
        if not auth:
            doc.close()
            raise PasswordError(f"'{path}' está protegido: contraseña incorrecta o ausente")
    elif password:
        auth = doc.authenticate(password)
    if for_edit and is_restricted(doc, auth):
        doc.close()
        raise PasswordError(f"'{Path(path).name}' tiene restricciones de modificación: "
                            "se necesita la contraseña de propietario (permisos)")
    return doc


def is_restricted(doc: pymupdf.Document, auth: int) -> bool:
    """``True`` si el documento está cifrado, no se abrió como propietario y no permite modificar."""
    return bool(doc.metadata.get("encryption")) and not (auth & 4) \
        and not (doc.permissions & pymupdf.PDF_PERM_MODIFY)


def save_pdf(doc: pymupdf.Document, output: PathLike, **kwargs) -> Path:
    """Guarda ``doc`` de forma atómica (archivo temporal + reemplazo).

    Por defecto conserva el cifrado que tuviera el documento original.
    """
    kwargs.setdefault("encryption", pymupdf.PDF_ENCRYPT_KEEP)
    kwargs.setdefault("garbage", 3)
    kwargs.setdefault("deflate", True)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    try:
        doc.save(tmp, **kwargs)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out

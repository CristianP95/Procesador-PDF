"""Editar: insertar imágenes (firmas) en páginas."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pymupdf

from ._io import PathLike, open_pdf, save_pdf
from .errors import ProcesadorPdfError

Rect = tuple[float, float, float, float]


def insert_images(
    input: PathLike,
    output: PathLike,
    placements: Sequence[tuple[int, Rect, PathLike]],
    *,
    keep_proportion: bool = True,
    password: str | None = None,
) -> Path:
    """Inserta imágenes (p. ej. una firma escaneada en PNG) en el PDF.

    ``placements``: lista de ``(pagina_base0, (x0, y0, x1, y1), ruta_imagen)``.
    Las coordenadas están en puntos PDF del sistema sin rotar de la página.
    """
    with open_pdf(input, password) as doc:
        for pno, rect, image in placements:
            if not 0 <= pno < doc.page_count:
                raise ProcesadorPdfError(f"La página {pno + 1} no existe")
            page = doc[pno]
            # Gira la imagen para que se vea derecha aunque la página esté rotada.
            page.insert_image(pymupdf.Rect(rect), filename=str(image),
                              keep_proportion=keep_proportion, rotate=(-page.rotation) % 360)
        return save_pdf(doc, output)


def insert_signature(input: PathLike, output: PathLike, page: int, rect: Rect, image: PathLike,
                     password: str | None = None) -> Path:
    """Atajo para insertar una sola firma."""
    return insert_images(input, output, [(page, rect, image)], password=password)

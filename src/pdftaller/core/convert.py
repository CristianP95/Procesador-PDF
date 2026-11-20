"""Convertir: imágenes a PDF."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pymupdf

from ._io import PathLike, save_pdf
from .errors import PdfTallerError

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp")


def images_to_pdf(images: Sequence[PathLike], output: PathLike, *, page_size: str | None = None,
                  margin: float = 0) -> Path:
    """Crea un PDF con una imagen por página.

    ``page_size=None`` usa el tamaño de cada imagen; ``"A4"`` o ``"letter"`` centra la imagen en esa hoja.
    """
    if not images:
        raise PdfTallerError("No hay imágenes")
    out = pymupdf.open()
    try:
        for img_path in images:
            try:
                img = pymupdf.open(str(img_path))
            except Exception as exc:
                raise PdfTallerError(f"No se pudo abrir la imagen '{img_path}': {exc}") from exc
            with img:
                w, h = img[0].rect.width, img[0].rect.height
            if page_size:
                pw, ph = pymupdf.paper_size(page_size)
                if (w > h) != (pw > ph):  # orientar la hoja como la imagen
                    pw, ph = ph, pw
            else:
                pw, ph = w + 2 * margin, h + 2 * margin
            page = out.new_page(width=pw, height=ph)
            page.insert_image(pymupdf.Rect(margin, margin, pw - margin, ph - margin),
                              filename=str(img_path), keep_proportion=True)
        return save_pdf(out, output)
    finally:
        out.close()

"""Marca de agua: texto o imagen sobre (o detrás de) las páginas."""
from __future__ import annotations

import math
from pathlib import Path

import pymupdf

from ._io import PathLike, open_pdf, save_pdf
from .errors import ProcesadorPdfError
from .pages import parse_page_ranges

POSITIONS = ("centro", "mosaico", "arriba", "abajo")


def _color(color) -> tuple[float, float, float]:
    """Acepta ``(r, g, b)`` en 0-1 o 0-255, o ``"#RRGGBB"``."""
    if isinstance(color, str):
        c = color.lstrip("#")
        if len(c) != 6:
            raise ProcesadorPdfError(f"Color no válido: {color}")
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    r, g, b = color
    return (r / 255, g / 255, b / 255) if max(r, g, b) > 1 else (float(r), float(g), float(b))


def _faded_image(image: PathLike, opacity: float) -> pymupdf.Pixmap:
    pix = pymupdf.Pixmap(str(image))
    if pix.colorspace and pix.colorspace.n not in (1, 3):      # CMYK u otros → RGB
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    while max(pix.width, pix.height) > 1600:
        pix.shrink(1)
    if not pix.alpha:
        pix = pymupdf.Pixmap(pix, 1)
    n = pix.n
    alphas = bytes(int(a * opacity) for a in pix.samples[n - 1::n])
    pix.set_alpha(alphas, premultiply=True)
    return pix


def _boxes(rect: pymupdf.Rect, w: float, h: float, position: str) -> list[pymupdf.Point]:
    """Centros donde dibujar la marca (coordenadas visibles de la página)."""
    if position == "centro":
        return [pymupdf.Point(rect.width / 2, rect.height / 2)]
    if position == "arriba":
        return [pymupdf.Point(rect.width / 2, max(h, 30) / 2 + 24)]
    if position == "abajo":
        return [pymupdf.Point(rect.width / 2, rect.height - max(h, 30) / 2 - 24)]
    # mosaico: cuadrícula con desplazamiento en filas alternas
    step_x, step_y = max(w * 1.4, 120), max(h * 3, 110)
    pts = []
    row = 0
    y = step_y / 2
    while y < rect.height + step_y / 2:
        x = step_x / 2 + (step_x / 2 if row % 2 else 0)
        while x < rect.width + step_x / 2:
            pts.append(pymupdf.Point(x, y))
            x += step_x
        y += step_y
        row += 1
    return pts


def apply_watermark(
    doc: pymupdf.Document,
    *,
    text: str | None = None,
    image: PathLike | None = None,
    pages: list[int] | None = None,
    opacity: float = 0.25,
    rotation: float = 45,
    fontsize: float | None = None,
    color="#808080",
    position: str = "centro",
    behind: bool = False,
    scale: float = 0.5,
) -> int:
    """Aplica la marca de agua a un documento abierto (sin guardarlo). Devuelve las páginas marcadas."""
    if not (text and text.strip()) and not image:
        raise ProcesadorPdfError("Indique el texto o la imagen de la marca de agua")
    if position not in POSITIONS:
        raise ProcesadorPdfError(f"Posición no válida: {position}. Use {', '.join(POSITIONS)}")
    if not 0.02 <= opacity <= 1:
        raise ProcesadorPdfError("La opacidad debe estar entre 2 % y 100 %")
    rgb = _color(color)
    font = pymupdf.Font("helv")
    pix = _faded_image(image, opacity) if image else None
    targets = range(doc.page_count) if pages is None else pages
    count = 0
    for pno in targets:
        page = doc[pno]
        r = page.rect                      # tamaño visible (ya considera la rotación de la página)
        derot = page.derotation_matrix
        page_rot = page.rotation
        # Se dibuja con la página sin girar (coordenadas "reales") y luego se restaura el giro
        if page_rot:
            page.set_rotation(0)
        if pix is not None:
            # La imagen ocupa ``scale`` del ancho; los giros libres solo se aplican a texto
            w = r.width * scale if position != "mosaico" else min(r.width, r.height) * 0.22
            h = w * pix.height / pix.width
            for c in _boxes(r, w, h, position):
                box = pymupdf.Rect(c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2) * derot
                page.insert_image(box, pixmap=pix, overlay=not behind, keep_proportion=True,
                                  rotate=(-page_rot) % 360)
        else:
            lines = text.strip().splitlines()
            longest = max(lines, key=lambda t: font.text_length(t, 1))
            unit = font.text_length(longest, 1) or 1
            if fontsize:
                fs = fontsize
            elif position == "mosaico":
                fs = max(12, min(r.width, r.height) * 0.18 / unit * 1.6)
            else:
                ang = math.radians(rotation % 180)
                c_, s_ = abs(math.cos(ang)), abs(math.sin(ang))
                # largo máximo de la línea girada para que quepa en la página
                span = min(r.width / c_ if c_ > 1e-3 else 1e9, r.height / s_ if s_ > 1e-3 else 1e9)
                fs = min(0.8 * span / unit, r.height / (2.2 * len(lines)))
                if position != "centro":
                    fs = min(fs, 48)
            tw, th = unit * fs, fs * 1.2 * len(lines)
            for c in _boxes(r, tw, th, position):
                cu = c * derot             # centro en coordenadas sin girar
                m = pymupdf.Matrix(rotation + page_rot) if (rotation or page_rot) else None
                for i, line in enumerate(lines):
                    lw = font.text_length(line, fs)
                    # línea horizontal centrada en el centro y luego girada alrededor de él
                    dy = (i - (len(lines) - 1) / 2) * fs * 1.2
                    start = pymupdf.Point(cu.x - lw / 2, cu.y + dy + fs * 0.35)
                    page.insert_text(start, line, fontsize=fs, fontname="helv", color=rgb,
                                     fill_opacity=opacity, overlay=not behind,
                                     morph=(cu, m) if m else None)
        if page_rot:
            page.set_rotation(page_rot)
        count += 1
    return count


def watermark(
    input: PathLike,
    output: PathLike,
    text: str | None = None,
    *,
    image: PathLike | None = None,
    pages: str | None = None,
    opacity: float = 0.25,
    rotation: float = 45,
    fontsize: float | None = None,
    color="#808080",
    position: str = "centro",
    behind: bool = False,
    scale: float = 0.5,
    password: str | None = None,
) -> tuple[Path, int]:
    """Agrega una marca de agua de texto (p. ej. ``"CONFIDENCIAL"``) o de imagen (logo).

    - ``pages``: rango en texto base 1 (``"1-3,5"``); ``None`` = todas.
    - ``opacity``: 0.02–1. ``rotation``: grados (solo texto). ``color``: ``"#RRGGBB"`` o ``(r, g, b)``.
    - ``position``: ``"centro"``, ``"mosaico"`` (repetida en toda la hoja), ``"arriba"`` o ``"abajo"``.
    - ``behind=True`` la dibuja detrás del contenido (se ve en zonas blancas; no tapa el texto).
    - ``scale``: ancho de la imagen respecto a la página (0–1).

    Devuelve ``(ruta_salida, páginas_marcadas)``.
    """
    with open_pdf(input, password) as doc:
        sel = sorted(set(parse_page_ranges(pages, doc.page_count))) if pages and pages.strip() else None
        n = apply_watermark(doc, text=text, image=image, pages=sel, opacity=opacity, rotation=rotation,
                            fontsize=fontsize, color=color, position=position, behind=behind, scale=scale)
        return save_pdf(doc, output), n

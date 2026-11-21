"""Optimizar: comprimir, reparar y reconocer texto (OCR)."""
from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from ._io import PathLike, open_pdf, save_pdf
from .errors import PdfTallerError

# nivel -> (umbral dpi, dpi objetivo, calidad JPEG)
COMPRESS_LEVELS = {
    "baja": (None, 0, 0),          # solo limpieza de estructura y fuentes, sin tocar imágenes
    "media": (200, 150, 80),       # buena calidad para pantalla e impresión de oficina
    "alta": (120, 96, 60),         # el más pequeño; para enviar por correo/web
}


@dataclass
class SizeReport:
    path: Path
    before: int
    after: int

    @property
    def saved_percent(self) -> float:
        return 100 * (1 - self.after / self.before) if self.before else 0.0

    def message(self) -> str:
        mb = lambda n: f"{n / 1_048_576:.2f} MB" if n >= 1_048_576 else f"{n / 1024:.0f} KB"
        if self.after >= self.before:
            return f"El archivo ya estaba optimizado ({mb(self.before)})."
        return f"{mb(self.before)} → {mb(self.after)}  (−{self.saved_percent:.0f} %)"


def compress(input: PathLike, output: PathLike, level: str = "media", *, gray: bool = False,
             password: str | None = None) -> SizeReport:
    """Reduce el tamaño: reduce resolución/recomprime imágenes, recorta fuentes y limpia la estructura.

    ``level``: ``"baja"`` (sin pérdida), ``"media"`` o ``"alta"``. ``gray=True`` pasa las imágenes a grises.
    Si el resultado no es más pequeño se conserva el original.
    """
    if level not in COMPRESS_LEVELS:
        raise PdfTallerError(f"Nivel no válido: {level}. Use {', '.join(COMPRESS_LEVELS)}")
    src = Path(input)
    before = src.stat().st_size
    threshold, target, quality = COMPRESS_LEVELS[level]
    with open_pdf(src, password) as doc:
        if threshold:
            doc.rewrite_images(dpi_threshold=threshold, dpi_target=target, quality=quality,
                               lossy=True, lossless=True, bitonal=True, color=True, gray=True,
                               set_to_gray=gray)
        elif gray:
            doc.rewrite_images(set_to_gray=True, quality=90)
        try:
            doc.subset_fonts()
        except Exception:
            pass  # algunas fuentes no se pueden recortar; no es crítico
        doc.scrub(metadata=False, xml_metadata=False, attached_files=False, embedded_files=False,
                  thumbnails=True, reset_fields=False, reset_responses=False, javascript=False,
                  clean_pages=True, hidden_text=False, redactions=False, remove_links=False)
        out = save_pdf(doc, output, garbage=4, clean=True, deflate_images=True, deflate_fonts=True,
                       use_objstms=1)
    after = out.stat().st_size
    if after >= before and out.resolve() != src.resolve():
        out.write_bytes(src.read_bytes())
        after = before
    return SizeReport(out, before, after)


@dataclass
class RepairReport:
    path: Path
    was_damaged: bool
    pages: int
    problems: list[str]

    def message(self) -> str:
        if self.was_damaged:
            return (f"Se reparó el archivo ({self.pages} páginas recuperadas).\n" +
                    "\n".join(f"• {p}" for p in self.problems))
        return f"No se encontraron daños. Se reescribió limpio ({self.pages} páginas)."


def repair(input: PathLike, output: PathLike, password: str | None = None) -> RepairReport:
    """Reconstruye un PDF dañado (tabla de objetos rota, archivo truncado, etc.)."""
    problems: list[str] = []
    pymupdf.TOOLS.mupdf_warnings(reset=True)
    try:
        doc = pymupdf.open(stream=Path(input).read_bytes(), filetype="pdf")
    except Exception as exc:
        raise PdfTallerError(f"El archivo está demasiado dañado para recuperarlo: {exc}") from exc
    try:
        if doc.needs_pass and not (password and doc.authenticate(password)):
            raise PdfTallerError("El archivo está protegido: indique la contraseña")
        warnings = pymupdf.TOOLS.mupdf_warnings()
        damaged = bool(doc.is_repaired) or bool(warnings)
        if warnings:
            problems += [w for w in warnings.splitlines() if w.strip()][:10]
        good = []
        for page in doc:
            try:
                page.get_text("text")
                page.get_pixmap(matrix=pymupdf.Matrix(0.1, 0.1))
                good.append(page.number)
            except Exception as exc:
                damaged = True
                problems.append(f"Página {page.number + 1} ilegible, se omitió: {exc}")
        if not good:
            raise PdfTallerError("No se pudo recuperar ninguna página")
        if len(good) != doc.page_count:
            doc.select(good)
        out = save_pdf(doc, output, garbage=4, clean=True)
        return RepairReport(out, damaged, len(good), problems)
    finally:
        doc.close()


# ---------------------------------------------------------------- OCR

def find_tessdata() -> str | None:
    """Busca la carpeta ``tessdata`` de Tesseract (incluida con la app o instalada en el sistema)."""
    candidates = []
    if os.environ.get("TESSDATA_PREFIX"):
        candidates.append(os.environ["TESSDATA_PREFIX"])
    base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    candidates += [base / "tessdata", Path(sys.executable).parent / "tessdata"]
    candidates += [
        r"C:\Program Files\Tesseract-OCR\tessdata",
        r"C:\Program Files (x86)\Tesseract-OCR\tessdata",
        str(Path.home() / "AppData/Local/Programs/Tesseract-OCR/tessdata"),
        "/usr/share/tesseract-ocr/5/tessdata", "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/share/tessdata", "/opt/homebrew/share/tessdata", "/usr/local/share/tessdata",
    ]
    for c in candidates:
        p = Path(c)
        if p.is_dir() and any(p.glob("*.traineddata")):
            return str(p)
    return None


def ocr_languages(tessdata: str | None = None) -> list[str]:
    td = tessdata or find_tessdata()
    if not td:
        return []
    return sorted(p.stem for p in Path(td).glob("*.traineddata") if p.stem != "osd")


@dataclass
class OcrReport:
    path: Path
    pages_ocr: int
    pages_skipped: int

    def message(self) -> str:
        msg = f"Texto reconocido en {self.pages_ocr} página(s)."
        if self.pages_skipped:
            msg += f" {self.pages_skipped} ya tenían texto y se dejaron igual."
        return msg


def ocr(
    input: PathLike,
    output: PathLike,
    *,
    language: str = "spa+eng",
    dpi: int = 300,
    only_without_text: bool = True,
    tessdata: str | None = None,
    password: str | None = None,
    progress: Callable[[int, int], bool | None] | None = None,
) -> OcrReport:
    """Hace buscable y copiable el texto de páginas escaneadas.

    Cada página escaneada se reemplaza por su imagen con una capa de texto invisible encima.
    ``progress(i, total)`` se llama por página; si devuelve ``False`` se cancela.
    Requiere los datos de Tesseract (``tessdata``) con el idioma pedido (p. ej. ``spa``).
    """
    td = tessdata or find_tessdata()
    if not td:
        raise PdfTallerError(
            "No se encontraron los datos de OCR (Tesseract). Instale Tesseract para Windows "
            "(https://github.com/UB-Mannheim/tesseract/wiki) con el idioma español, "
            "o copie la carpeta 'tessdata' junto al programa.")
    missing = [l for l in language.split("+") if not (Path(td) / f"{l}.traineddata").exists()]
    if missing:
        raise PdfTallerError(f"Faltan idiomas de OCR en {td}: {', '.join(missing)}")
    done = skipped = 0
    with open_pdf(input, password) as doc:
        out = pymupdf.open()
        try:
            total = doc.page_count
            for i, page in enumerate(doc):
                if progress and progress(i, total) is False:
                    raise PdfTallerError("OCR cancelado")
                if only_without_text and page.get_text("text").strip():
                    out.insert_pdf(doc, from_page=i, to_page=i)
                    skipped += 1
                    continue
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                # El pixmap guarda su resolución, así la página OCR conserva el tamaño original.
                one = pymupdf.open("pdf", pix.pdfocr_tobytes(compress=True, language=language, tessdata=td))
                out.insert_pdf(one)
                one.close()
                done += 1
            path = save_pdf(out, output)
        finally:
            out.close()
    if progress:
        progress(total, total)
    return OcrReport(path, done, skipped)

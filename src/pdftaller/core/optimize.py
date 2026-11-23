"""Optimizar: analizar, comprimir, reparar y reconocer texto (OCR)."""
from __future__ import annotations

import os
import sys
import tempfile
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


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.2f} MB" if n >= 1_048_576 else f"{n / 1024:.0f} KB"


@dataclass
class SizeReport:
    path: Path
    before: int
    after: int

    @property
    def saved_percent(self) -> float:
        return 100 * (1 - self.after / self.before) if self.before else 0.0

    def message(self) -> str:
        if self.after >= self.before:
            return f"El archivo ya estaba optimizado ({_mb(self.before)})."
        return f"{_mb(self.before)} → {_mb(self.after)}  (−{self.saved_percent:.0f} %)"


def compress(input: PathLike, output: PathLike, level: str = "media", *, gray: bool = False,
             dpi: int | None = None, quality: int | None = None, strip: bool = False,
             password: str | None = None) -> SizeReport:
    """Reduce el tamaño: baja la resolución / recomprime imágenes, recorta fuentes y limpia la estructura.

    - ``level``: ``"baja"`` (sin pérdida), ``"media"`` o ``"alta"``.
    - ``dpi`` / ``quality`` (10-100): ajuste a medida que reemplaza los valores del nivel.
    - ``gray=True`` pasa las imágenes a escala de grises.
    - ``strip=True`` quita además metadatos, adjuntos y JavaScript.

    Si el resultado no es más pequeño se conserva el original.
    """
    if level not in COMPRESS_LEVELS:
        raise PdfTallerError(f"Nivel no válido: {level}. Use {', '.join(COMPRESS_LEVELS)}")
    threshold, target, q = COMPRESS_LEVELS[level]
    if dpi:
        if not 36 <= dpi <= 600:
            raise PdfTallerError("La resolución debe estar entre 36 y 600 ppp")
        threshold, target = int(dpi * 1.3), dpi
    if quality:
        if not 10 <= quality <= 100:
            raise PdfTallerError("La calidad JPEG debe estar entre 10 y 100")
        q = quality
        if not threshold:
            threshold, target = 10_000, 0     # solo recomprimir, sin bajar la resolución
    src = Path(input)
    before = src.stat().st_size
    with open_pdf(src, password) as doc:
        if threshold:
            doc.rewrite_images(dpi_threshold=threshold, dpi_target=target, quality=q or 80,
                               lossy=True, lossless=True, bitonal=True, color=True, gray=True,
                               set_to_gray=gray)
        elif gray:
            doc.rewrite_images(set_to_gray=True, quality=90)
        try:
            doc.subset_fonts()
        except Exception:
            pass  # algunas fuentes no se pueden recortar; no es crítico
        doc.scrub(metadata=strip, xml_metadata=strip, attached_files=strip, embedded_files=strip,
                  thumbnails=True, reset_fields=False, reset_responses=False, javascript=strip,
                  clean_pages=True, hidden_text=False, redactions=False, remove_links=False)
        out = save_pdf(doc, output, garbage=4, clean=True, deflate_images=True, deflate_fonts=True,
                       use_objstms=1)
    after = out.stat().st_size
    if after >= before and out.resolve() != src.resolve():
        out.write_bytes(src.read_bytes())
        after = before
    return SizeReport(out, before, after)


def estimate_compression(input: PathLike, levels=("baja", "media", "alta"), *,
                         password: str | None = None, **options) -> dict[str, int]:
    """Tamaño en bytes que tendría el archivo con cada nivel (no modifica nada)."""
    sizes = {}
    with tempfile.TemporaryDirectory(prefix="pdftaller_est_") as tmp:
        for lv in levels:
            sizes[lv] = compress(input, Path(tmp) / f"{lv}.pdf", lv, password=password, **options).after
    return sizes


# ---------------------------------------------------------------- analizar

@dataclass
class SizeAnalysis:
    """Qué ocupa espacio dentro del PDF."""
    total: int
    pages: int
    images: int = 0
    image_count: int = 0
    fonts: int = 0
    font_count: int = 0
    content: int = 0
    attachments: int = 0
    scanned_pages: int = 0       # páginas sin texto (probablemente escaneadas)
    max_image_dpi: int = 0
    has_metadata: bool = False

    @property
    def other(self) -> int:
        return max(0, self.total - self.images - self.fonts - self.content)

    def recommendation(self) -> str:
        if self.images > self.total * 0.5 and self.max_image_dpi > 160:
            return "media"
        if self.images > self.total * 0.5:
            return "alta"
        return "baja"

    def message(self) -> str:
        pct = (lambda n: f"{100 * n / self.total:.0f} %") if self.total else (lambda n: "0 %")
        lines = [f"Tamaño total: {_mb(self.total)} · {self.pages} página(s)",
                 f"• Imágenes: {_mb(self.images)} ({pct(self.images)}) en {self.image_count} imagen(es)"
                 + (f", hasta {self.max_image_dpi} ppp" if self.max_image_dpi else ""),
                 f"• Fuentes: {_mb(self.fonts)} ({pct(self.fonts)}) en {self.font_count} archivo(s)",
                 f"• Texto y dibujos de las páginas: {_mb(self.content)} ({pct(self.content)})",
                 f"• Estructura y otros: {_mb(self.other)} ({pct(self.other)})"]
        if self.attachments:
            lines.append(f"• Archivos adjuntos: {self.attachments}")
        lines.append("")
        if self.scanned_pages:
            lines.append(f"{self.scanned_pages} página(s) parecen escaneadas (sin texto): use «Reconocer "
                         "texto» para poder buscar, copiar y censurar su contenido.")
        rec = self.recommendation()
        if rec == "baja" and self.images <= self.total * 0.5:
            lines.append("Recomendación: compresión baja (sin pérdida). Las imágenes no son lo que más ocupa.")
        else:
            lines.append(f"Recomendación: compresión {rec} (las imágenes ocupan la mayor parte).")
        return "\n".join(lines)


def analyze(input: PathLike, password: str | None = None) -> SizeAnalysis:
    """Analiza qué ocupa espacio en el PDF (imágenes, fuentes, contenido) y recomienda un nivel."""
    src = Path(input)
    with open_pdf(src, password, for_edit=False) as doc:
        a = SizeAnalysis(total=src.stat().st_size, pages=doc.page_count)
        a.has_metadata = any(v for k, v in (doc.metadata or {}).items() if k not in ("format", "encryption"))
        try:
            a.attachments = doc.embfile_count()
        except Exception:
            pass
        font_files: set[int] = set()
        content_x: set[int] = set()
        for page in doc:
            content_x.update(page.get_contents())
            if not page.get_text("text").strip():
                a.scanned_pages += 1
            for img in page.get_image_info():
                bbox = pymupdf.Rect(img["bbox"])
                if bbox.width > 1 and img.get("width"):
                    a.max_image_dpi = max(a.max_image_dpi, int(img["width"] / (bbox.width / 72)))
        for x in range(1, doc.xref_length()):
            try:
                if not doc.xref_is_stream(x):
                    for key in ("FontFile", "FontFile2", "FontFile3"):
                        t, v = doc.xref_get_key(x, key)
                        if t == "xref":
                            font_files.add(int(v.split()[0]))
                    continue
                size = len(doc.xref_stream_raw(x) or b"")
                subtype = doc.xref_get_key(x, "Subtype")[1]
            except Exception:
                continue
            if subtype == "/Image":
                a.images += size
                a.image_count += 1
            elif x in content_x:
                a.content += size
        for x in font_files:
            try:
                a.fonts += len(doc.xref_stream_raw(x) or b"")
            except Exception:
                pass
        a.font_count = len(font_files)
        return a


# ---------------------------------------------------------------- reparar

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
    words: int = 0

    def message(self) -> str:
        msg = f"Texto reconocido en {self.pages_ocr} página(s): {self.words} palabra(s)."
        if self.pages_skipped:
            msg += f" {self.pages_skipped} ya tenían texto y se dejaron igual."
        if self.pages_ocr and not self.words:
            msg += "\nNo se reconoció ninguna palabra: pruebe otra resolución o idioma."
        return msg


_OCR_FONT: pymupdf.Font | None = None


def _overlay_words(page: pymupdf.Page, words) -> int:
    """Escribe cada palabra reconocida como texto invisible justo sobre su imagen en la página."""
    global _OCR_FONT
    if _OCR_FONT is None:
        _OCR_FONT = pymupdf.Font("helv")
    n = 0
    for w in words:
        r, word = pymupdf.Rect(w[:4]), w[4]
        if not word.strip() or r.is_empty:
            continue
        unit = _OCR_FONT.text_length(word, fontsize=1)
        fs = r.width / unit if unit else r.height
        fs = max(min(fs, r.height * 1.6), r.height * 0.5)
        page.insert_text(pymupdf.Point(r.x0, r.y1 - 0.2 * r.height), word, fontsize=fs,
                         fontname="helv", render_mode=3)   # 3 = texto invisible
        n += 1
    return n


def ocr(
    input: PathLike,
    output: PathLike,
    *,
    language: str = "spa+eng",
    dpi: int = 300,
    only_without_text: bool = True,
    keep_original: bool = True,
    tessdata: str | None = None,
    password: str | None = None,
    progress: Callable[[int, int], bool | None] | None = None,
) -> OcrReport:
    """Hace buscable y copiable el texto de páginas escaneadas.

    Con ``keep_original=True`` (recomendado) la página no se toca: se le agrega encima una capa de
    texto invisible, así no pierde calidad ni crece mucho. Con ``False`` (y siempre en páginas
    giradas) la página se reemplaza por su imagen a ``dpi`` con la capa de texto.
    ``progress(i, total)`` se llama por página; si devuelve ``False`` se cancela.
    Requiere los datos de Tesseract (``tessdata``) con el idioma pedido (p. ej. ``spa``).
    """
    td = tessdata or find_tessdata()
    if not td:
        raise PdfTallerError(
            "No se encontraron los datos para reconocer texto (Tesseract). Instale Tesseract para Windows "
            "(https://github.com/UB-Mannheim/tesseract/wiki) con el idioma español, "
            "o copie la carpeta 'tessdata' junto al programa.")
    missing = [l for l in language.split("+") if not (Path(td) / f"{l}.traineddata").exists()]
    if missing:
        raise PdfTallerError(f"Faltan idiomas para reconocer texto en {td}: {', '.join(missing)}")
    done = skipped = words = 0
    with open_pdf(input, password) as doc:
        total = doc.page_count
        raster: set[int] = set()
        for i, page in enumerate(doc):
            if progress and progress(i, total) is False:
                raise PdfTallerError("Reconocimiento de texto cancelado")
            if only_without_text and page.get_text("text").strip():
                skipped += 1
                continue
            if keep_original and page.rotation == 0:
                tp = page.get_textpage_ocr(language=language, dpi=dpi, full=True, tessdata=td)
                words += _overlay_words(page, page.get_text("words", textpage=tp))
            else:
                raster.add(i)
            done += 1
        if raster:
            out = pymupdf.open()
            try:
                for i in range(total):
                    if i not in raster:
                        out.insert_pdf(doc, from_page=i, to_page=i)
                        continue
                    pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
                    # El pixmap guarda su resolución, así la página OCR conserva el tamaño original.
                    one = pymupdf.open("pdf", pix.pdfocr_tobytes(compress=True, language=language, tessdata=td))
                    words += len(one[0].get_text("words"))
                    out.insert_pdf(one)
                    one.close()
                path = save_pdf(out, output)
            finally:
                out.close()
        else:
            path = save_pdf(doc, output)
    if progress:
        progress(total, total)
    return OcrReport(path, done, skipped, words)

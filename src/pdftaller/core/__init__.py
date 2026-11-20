"""Núcleo de PDF Taller: funciones puras sobre archivos, sin dependencia de la GUI.

Pensado para usarse igual desde la interfaz gráfica (V1) y desde scripts (V2).
Las páginas en parámetros de texto (``"1-3,5"``) son base 1; en listas de enteros son base 0.
"""
from .errors import PageRangeError, PasswordError, PdfTallerError
from .organize import delete_pages, extract_pages, merge, page_count, reorder, rotate_pages, split
from .pages import parse_page_ranges, parse_range_groups
from .security import CompareResult, PageDiff, compare, find_text, is_encrypted, protect, redact, unlock

__all__ = [
    "PdfTallerError", "PasswordError", "PageRangeError",
    "merge", "split", "extract_pages", "reorder", "delete_pages", "rotate_pages", "page_count",
    "parse_page_ranges", "parse_range_groups",
    "protect", "unlock", "is_encrypted", "compare", "CompareResult", "PageDiff", "find_text", "redact",
]

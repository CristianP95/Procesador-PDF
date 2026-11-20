"""Interpretación de rangos de páginas escritos por personas ("1-3, 5, 8-")."""
from __future__ import annotations

from .errors import PageRangeError


def parse_page_ranges(spec: str, page_count: int) -> list[int]:
    """Convierte ``"1-3,5,8-"`` en índices base 0. Las páginas son base 1 en el texto.

    ``"-3"`` = desde la primera hasta la 3; ``"8-"`` = desde la 8 hasta el final.
    Conserva el orden y las repeticiones escritas.
    """
    if not spec or not spec.strip():
        raise PageRangeError("El rango de páginas está vacío")
    result: list[int] = []
    for part in spec.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, b = (x.strip() for x in part.split("-", 1))
                start = int(a) if a else 1
                end = int(b) if b else page_count
            else:
                start = end = int(part)
        except ValueError:
            raise PageRangeError(f"Rango no válido: '{part}'") from None
        for n in (start, end):
            if not 1 <= n <= page_count:
                raise PageRangeError(f"La página {n} no existe (el documento tiene {page_count})")
        step = 1 if end >= start else -1
        result.extend(i - 1 for i in range(start, end + step, step))
    if not result:
        raise PageRangeError("El rango de páginas está vacío")
    return result


def parse_range_groups(spec: str, page_count: int) -> list[list[int]]:
    """``"1-3; 4-6"`` → grupos separados por ``;`` (cada grupo será un archivo)."""
    groups = [g for g in spec.split(";") if g.strip()]
    if not groups:
        raise PageRangeError("No se indicó ningún grupo de páginas")
    return [parse_page_ranges(g, page_count) for g in groups]

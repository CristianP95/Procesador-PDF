"""Ordenar: unir, dividir, reordenar, eliminar y rotar páginas."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pymupdf

from ._io import PathLike, open_pdf, save_pdf
from .errors import PageRangeError, ProcesadorPdfError
from .pages import parse_page_ranges, parse_range_groups


def page_count(path: PathLike, password: str | None = None) -> int:
    with open_pdf(path, password, for_edit=False) as doc:
        return doc.page_count


def merge(
    inputs: Sequence[PathLike],
    output: PathLike,
    page_ranges: Sequence[str | None] | None = None,
    passwords: Sequence[str | None] | None = None,
) -> Path:
    """Une varios PDF en ``output`` en el orden dado.

    ``page_ranges[i]`` (opcional) limita las páginas tomadas del archivo ``i``, p. ej. ``"1-3,5"``.
    """
    if not inputs:
        raise ProcesadorPdfError("No hay archivos para unir")
    result = pymupdf.open()
    try:
        for i, src_path in enumerate(inputs):
            pw = passwords[i] if passwords and i < len(passwords) else None
            spec = page_ranges[i] if page_ranges and i < len(page_ranges) else None
            with open_pdf(src_path, pw) as src:
                if spec:
                    for p in parse_page_ranges(spec, src.page_count):
                        result.insert_pdf(src, from_page=p, to_page=p)
                else:
                    result.insert_pdf(src)
        return save_pdf(result, output)
    finally:
        result.close()


def _write_pages(src: pymupdf.Document, pages: list[int], output: Path) -> Path:
    out = pymupdf.open()
    try:
        for p in pages:
            out.insert_pdf(src, from_page=p, to_page=p)
        return save_pdf(out, output)
    finally:
        out.close()


def split(
    input: PathLike,
    output_dir: PathLike,
    *,
    every: int | None = None,
    ranges: str | None = None,
    prefix: str | None = None,
    password: str | None = None,
) -> list[Path]:
    """Divide un PDF en varios archivos dentro de ``output_dir``.

    - ``every=N``: un archivo cada N páginas (``every=1`` = una página por archivo).
    - ``ranges="1-3; 4-6; 7-"``: un archivo por grupo separado por ``;``.
    """
    if (every is None) == (ranges is None):
        raise ProcesadorPdfError("Indique 'every' o 'ranges' (solo uno)")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = prefix or Path(input).stem
    with open_pdf(input, password) as src:
        n = src.page_count
        if every is not None:
            if every < 1:
                raise PageRangeError("'every' debe ser 1 o mayor")
            groups = [list(range(s, min(s + every, n))) for s in range(0, n, every)]
        else:
            groups = parse_range_groups(ranges, n)
        width = len(str(len(groups)))
        return [
            _write_pages(src, g, out_dir / f"{stem}_{i:0{width}d}.pdf")
            for i, g in enumerate(groups, start=1)
        ]


def extract_pages(input: PathLike, output: PathLike, pages: str, password: str | None = None) -> Path:
    """Guarda en ``output`` solo las páginas indicadas (``"1-3,7"``)."""
    with open_pdf(input, password) as src:
        return _write_pages(src, parse_page_ranges(pages, src.page_count), Path(output))


def reorder(input: PathLike, output: PathLike, order: Sequence[int], password: str | None = None) -> Path:
    """Reescribe el PDF con las páginas en ``order`` (índices base 0).

    Páginas omitidas se eliminan; repetidas se duplican.
    """
    with open_pdf(input, password) as doc:
        n = doc.page_count
        bad = [p for p in order if not 0 <= p < n]
        if bad or not order:
            raise PageRangeError(f"Orden no válido para {n} páginas: {list(order)}")
        doc.select(list(order))
        return save_pdf(doc, output)


def delete_pages(input: PathLike, output: PathLike, pages: Sequence[int], password: str | None = None) -> Path:
    """Elimina las páginas indicadas (índices base 0)."""
    with open_pdf(input, password) as doc:
        drop = set(pages)
        keep = [i for i in range(doc.page_count) if i not in drop]
        if not keep:
            raise PageRangeError("No se pueden eliminar todas las páginas")
        doc.select(keep)
        return save_pdf(doc, output)


def rotate_pages(
    input: PathLike,
    output: PathLike,
    pages: Sequence[int] | None,
    degrees: int,
    password: str | None = None,
) -> Path:
    """Rota las páginas (base 0; ``None`` = todas) en múltiplos de 90 grados."""
    if degrees % 90:
        raise ProcesadorPdfError("La rotación debe ser múltiplo de 90")
    with open_pdf(input, password) as doc:
        targets = range(doc.page_count) if pages is None else pages
        for i in targets:
            page = doc[i]
            page.set_rotation((page.rotation + degrees) % 360)
        return save_pdf(doc, output)

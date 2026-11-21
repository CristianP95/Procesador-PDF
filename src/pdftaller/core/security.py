"""Seguridad: proteger, desbloquear, comparar y censurar."""
from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from ._io import PathLike, open_pdf, save_pdf
from .errors import PasswordError, PdfTallerError


# ---------------------------------------------------------------- proteger / desbloquear

def is_encrypted(path: PathLike) -> bool:
    """``True`` si el PDF pide contraseña para abrirse (ver también ``permissions``)."""
    with pymupdf.open(Path(path)) as doc:
        return bool(doc.needs_pass)


def protect(
    input: PathLike,
    output: PathLike,
    user_password: str | None,
    owner_password: str | None = None,
    *,
    allow_print: bool = True,
    allow_copy: bool = False,
    allow_modify: bool = False,
    allow_annotate: bool = False,
    password: str | None = None,
) -> Path:
    """Cifra el PDF con AES-256.

    - ``user_password``: contraseña para ABRIR. Puede ser vacía: se abre sin contraseña pero
      con las restricciones activas.
    - ``owner_password``: contraseña de PERMISOS (propietario). Quien abre con ella no tiene
      restricciones, por eso debe ser distinta de la de apertura. Si se omite, se usa la de
      apertura y los ``allow_*`` no tendrán efecto para quien la conozca.
    - ``allow_*``: lo que puede hacer quien abre con la contraseña de apertura (o sin contraseña).
    """
    user_password = user_password or ""
    owner_password = owner_password or user_password
    if not owner_password:
        raise PdfTallerError("Indique al menos una contraseña (de apertura o de permisos)")
    perm = 0
    if allow_print:
        perm |= pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ
    if allow_copy:
        perm |= pymupdf.PDF_PERM_COPY | pymupdf.PDF_PERM_ACCESSIBILITY
    if allow_modify:
        perm |= pymupdf.PDF_PERM_MODIFY | pymupdf.PDF_PERM_ASSEMBLE
    if allow_annotate:
        perm |= pymupdf.PDF_PERM_ANNOTATE | pymupdf.PDF_PERM_FORM
    with open_pdf(input, password) as doc:
        return save_pdf(
            doc,
            output,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=user_password,
            owner_pw=owner_password,
            permissions=perm,
        )


def permissions(path: PathLike, password: str | None = None) -> dict[str, bool]:
    """Permisos efectivos al abrir el PDF con ``password`` (o sin contraseña)."""
    with open_pdf(path, password, for_edit=False) as doc:
        p = doc.permissions
        return {
            "imprimir": bool(p & pymupdf.PDF_PERM_PRINT),
            "copiar": bool(p & pymupdf.PDF_PERM_COPY),
            "modificar": bool(p & pymupdf.PDF_PERM_MODIFY),
            "comentar": bool(p & pymupdf.PDF_PERM_ANNOTATE),
        }


def unlock(input: PathLike, output: PathLike, password: str) -> Path:
    """Quita la protección de un PDF. Requiere la contraseña de propietario
    (si el PDF se protegió con una sola contraseña, esa misma sirve)."""
    with open_pdf(input, password, for_edit=False) as doc:
        if doc.metadata.get("encryption"):
            if not password or not (doc.authenticate(password) & 4):  # 4 = propietario
                raise PasswordError("Se necesita la contraseña de propietario para quitar la protección")
        return save_pdf(doc, output, encryption=pymupdf.PDF_ENCRYPT_NONE)


# ---------------------------------------------------------------- comparar

@dataclass
class PageDiff:
    page: int  # base 1
    added: list[str] = field(default_factory=list)  # líneas solo en B
    removed: list[str] = field(default_factory=list)  # líneas solo en A
    visual_change: float = 0.0  # fracción de píxeles distintos (0..1)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.visual_change > 0)


@dataclass
class CompareResult:
    pages_a: int
    pages_b: int
    pages: list[PageDiff]

    @property
    def identical(self) -> bool:
        return self.pages_a == self.pages_b and not any(p.changed for p in self.pages)

    def summary(self) -> str:
        if self.identical:
            return "Los documentos son iguales."
        lines = [f"Documento A: {self.pages_a} páginas · Documento B: {self.pages_b} páginas"]
        for p in self.pages:
            if not p.changed:
                continue
            lines.append(f"\n— Página {p.page}")
            lines += [f"  - {t}" for t in p.removed]
            lines += [f"  + {t}" for t in p.added]
            if p.visual_change and not (p.added or p.removed):
                lines.append(f"  (cambio visual: {p.visual_change:.1%} de la página)")
        return "\n".join(lines)


def _page_lines(page: pymupdf.Page | None) -> list[str]:
    if page is None:
        return []
    return [ln.strip() for ln in page.get_text("text").splitlines() if ln.strip()]


def _visual_diff(pa: pymupdf.Page, pb: pymupdf.Page, dpi: int) -> float:
    a = pa.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    b = pb.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    if (a.width, a.height) != (b.width, b.height):
        return 1.0
    sa, sb = a.samples, b.samples
    diff = sum(1 for x, y in zip(sa, sb) if abs(x - y) > 32)
    return diff / len(sa) if sa else 0.0


def compare(
    a: PathLike,
    b: PathLike,
    *,
    visual: bool = False,
    dpi: int = 36,
    password_a: str | None = None,
    password_b: str | None = None,
) -> CompareResult:
    """Compara dos PDF página por página (texto y, opcionalmente, imagen)."""
    with open_pdf(a, password_a, for_edit=False) as da, open_pdf(b, password_b, for_edit=False) as db:
        diffs: list[PageDiff] = []
        for i in range(max(da.page_count, db.page_count)):
            pa = da[i] if i < da.page_count else None
            pb = db[i] if i < db.page_count else None
            la, lb = _page_lines(pa), _page_lines(pb)
            pd = PageDiff(page=i + 1)
            for op, a0, a1, b0, b1 in difflib.SequenceMatcher(None, la, lb, autojunk=False).get_opcodes():
                if op in ("replace", "delete"):
                    pd.removed += la[a0:a1]
                if op in ("replace", "insert"):
                    pd.added += lb[b0:b1]
            if pa is None or pb is None:
                pd.visual_change = 1.0
            elif visual:
                pd.visual_change = _visual_diff(pa, pb, dpi)
            diffs.append(pd)
        return CompareResult(da.page_count, db.page_count, diffs)


# ---------------------------------------------------------------- censurar

Rect = tuple[float, float, float, float]


def find_text(input: PathLike, terms: Iterable[str], *, regex: bool = False,
              ignore_case: bool = True, password: str | None = None) -> dict[int, list[Rect]]:
    """Devuelve las zonas (por página, base 0) donde aparecen los términos."""
    with open_pdf(input, password, for_edit=False) as doc:
        return {i: [tuple(r) for r in rects] for i, rects in _find(doc, terms, regex, ignore_case).items()}


def _find(doc: pymupdf.Document, terms: Iterable[str], regex: bool, ignore_case: bool) -> dict[int, list[pymupdf.Rect]]:
    terms = [t for t in terms if t]
    flags = re.IGNORECASE if ignore_case else 0
    hits: dict[int, list[pymupdf.Rect]] = {}
    for page in doc:
        rects: list[pymupdf.Rect] = []
        if regex:
            text = page.get_text("text")
            needles = {m.group(0) for t in terms for m in re.finditer(t, text, flags) if m.group(0).strip()}
        else:
            needles = set(terms)
        for needle in needles:
            # search_for ya ignora mayúsculas/minúsculas
            rects += page.search_for(needle)
        if rects:
            hits[page.number] = rects
    return hits


def redact(
    input: PathLike,
    output: PathLike,
    terms: Sequence[str] = (),
    *,
    regex: bool = False,
    areas: Mapping[int, Sequence[Rect]] | None = None,
    fill: tuple[float, float, float] = (0, 0, 0),
    remove_metadata: bool = True,
    password: str | None = None,
) -> tuple[Path, int]:
    """Censura de verdad: elimina el texto/imagen bajo cada zona y la cubre con ``fill``.

    ``terms``: textos (o expresiones regulares si ``regex=True``) a censurar.
    ``areas``: zonas extra ``{pagina_base0: [(x0, y0, x1, y1), ...]}`` en puntos PDF.
    Devuelve ``(ruta_salida, número_de_zonas_censuradas)``.
    """
    with open_pdf(input, password) as doc:
        targets = _find(doc, terms, regex, ignore_case=True)
        for pno, rects in (areas or {}).items():
            targets.setdefault(pno, []).extend(pymupdf.Rect(r) for r in rects)
        count = 0
        for pno, rects in targets.items():
            page = doc[pno]
            for r in rects:
                page.add_redact_annot(r, fill=fill)
                count += 1
            page.apply_redactions()
        if remove_metadata:
            doc.set_metadata({})
            doc.del_xml_metadata()
        return save_pdf(doc, output), count

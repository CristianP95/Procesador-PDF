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


ALL_PERMISSIONS = {"imprimir", "copiar", "modificar", "comentar"}


def generate_password(length: int = 16) -> str:
    """Contraseña aleatoria fuerte (sin caracteres confusos como 0/O o l/1)."""
    import secrets
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789-_.!"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def protect(
    input: PathLike,
    output: PathLike,
    user_password: str | None,
    owner_password: str | None = None,
    *,
    allow_print: bool | None = None,
    allow_copy: bool | None = None,
    allow_modify: bool | None = None,
    allow_annotate: bool | None = None,
    password: str | None = None,
) -> Path:
    """Cifra el PDF con AES-256.

    - ``user_password``: contraseña para ABRIR. Puede ser vacía: el PDF se abre sin contraseña
      pero con las restricciones activas.
    - ``owner_password``: contraseña de PERMISOS (propietario). Quien abre con ella no tiene
      restricciones, por eso **debe ser distinta** de la de apertura (puede crear una con
      :func:`generate_password`; guárdela, sin ella no se puede desbloquear).
    - ``allow_*``: lo que puede hacer quien abre con la contraseña de apertura (o sin contraseña).
      Por defecto: imprimir sí; copiar, modificar y comentar no.

    Si solo se da ``user_password`` (sin contraseña de permisos ni ``allow_*``), el PDF queda
    protegido para abrir pero sin restricciones: quien conoce la contraseña puede todo.

    Las restricciones las aplican los lectores que respetan la norma PDF (Adobe Reader,
    PDF Taller…); algunos visores de navegador ignoran parte de ellas.
    """
    user_password = user_password or ""
    owner_password = owner_password or ""
    explicit = [v for v in (allow_print, allow_copy, allow_modify, allow_annotate) if v is not None]
    if not owner_password:
        if any(v is False for v in explicit):
            raise PdfTallerError("Para aplicar restricciones indique una contraseña de permisos distinta "
                                 "de la de apertura (puede generarla con generate_password())")
        # Solo contraseña de apertura: sin restricciones (serían inútiles con una sola contraseña)
        allow_print = allow_copy = allow_modify = allow_annotate = True
        owner_password = user_password
    allow_print = True if allow_print is None else allow_print
    allow_copy, allow_modify, allow_annotate = (bool(v) for v in (allow_copy, allow_modify, allow_annotate))
    restricted = not (allow_print and allow_copy and allow_modify and allow_annotate)
    if not owner_password:
        raise PdfTallerError("Indique al menos una contraseña (de apertura o de permisos)")
    if restricted and owner_password == user_password:
        raise PdfTallerError("La contraseña de permisos debe ser distinta de la de apertura: "
                             "quien abre con la de permisos no tiene restricciones")
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
        out = save_pdf(
            doc,
            output,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=user_password,
            owner_pw=owner_password,
            permissions=perm,
        )
    # Comprobación: al reabrir con la contraseña de apertura deben verse justo esas restricciones.
    wanted = {"imprimir": allow_print, "copiar": allow_copy, "modificar": allow_modify, "comentar": allow_annotate}
    got = permissions(out, user_password or None)
    if got != wanted:
        raise PdfTallerError(f"Las restricciones no quedaron aplicadas correctamente: {got}")
    return out


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
    return {p: [r for r, _ in hits] for p, hits in
            find_text_labeled(input, terms, regex=regex, ignore_case=ignore_case, password=password).items()}


def find_text_labeled(input: PathLike, terms: Iterable[str], *, regex: bool = False,
                      ignore_case: bool = True, password: str | None = None) -> dict[int, list[tuple[Rect, str]]]:
    """Como :func:`find_text`, pero cada zona va con el texto encontrado: ``{pag: [(rect, texto)]}``."""
    with open_pdf(input, password, for_edit=False) as doc:
        return {i: [(tuple(r), t) for r, t in hits] for i, hits in _find(doc, terms, regex, ignore_case).items()}


def _find(doc: pymupdf.Document, terms: Iterable[str], regex: bool,
          ignore_case: bool) -> dict[int, list[tuple[pymupdf.Rect, str]]]:
    terms = [t for t in terms if t]
    flags = re.IGNORECASE if ignore_case else 0
    if regex:
        for t in terms:
            try:
                re.compile(t)
            except re.error as exc:
                raise PdfTallerError(f"Expresión regular no válida «{t}»: {exc}") from exc
    hits: dict[int, list[tuple[pymupdf.Rect, str]]] = {}
    for page in doc:
        found: list[tuple[pymupdf.Rect, str]] = []
        if regex:
            text = page.get_text("text")
            needles = {m.group(0) for t in terms for m in re.finditer(t, text, flags) if m.group(0).strip()}
        else:
            needles = set(terms)
        for needle in sorted(needles):
            # search_for ya ignora mayúsculas/minúsculas
            found += [(r, needle) for r in page.search_for(needle)]
        if found:
            hits[page.number] = found
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
        targets = {p: [r for r, _ in h] for p, h in _find(doc, terms, regex, ignore_case=True).items()}
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

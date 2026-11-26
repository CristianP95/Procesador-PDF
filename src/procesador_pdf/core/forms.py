"""Formularios PDF: leer los campos, diligenciarlos (uno o en lote desde CSV) y aplanarlos."""
from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from ._io import PathLike, open_pdf, save_pdf
from .errors import PasswordError, ProcesadorPdfError

# Tipos que se pueden diligenciar
KINDS = {
    pymupdf.PDF_WIDGET_TYPE_TEXT: "texto",
    pymupdf.PDF_WIDGET_TYPE_CHECKBOX: "casilla",
    pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: "opción",
    pymupdf.PDF_WIDGET_TYPE_COMBOBOX: "lista",
    pymupdf.PDF_WIDGET_TYPE_LISTBOX: "lista",
}
_READONLY = 1  # bit 1 de /Ff


@dataclass
class FormField:
    name: str
    kind: str                      # "texto" | "casilla" | "opción" | "lista"
    value: str | bool
    page: int                      # base 0 (primera aparición)
    options: list[str] = field(default_factory=list)   # listas y grupos de opciones
    readonly: bool = False
    label: str = ""                # texto de ayuda del campo (tooltip), si lo tiene
    multiline: bool = False
    max_length: int = 0


def _open_for_filling(input: PathLike, password: str | None) -> pymupdf.Document:
    doc = open_pdf(input, password, for_edit=False)
    if doc.metadata.get("encryption"):
        auth = doc.authenticate(password) if password else 0
        perms = doc.permissions
        if not (auth & 4) and not (perms & (pymupdf.PDF_PERM_FORM | pymupdf.PDF_PERM_MODIFY)):
            doc.close()
            raise PasswordError("El documento no permite rellenar formularios: "
                                "se necesita la contraseña de permisos")
    return doc


def list_fields(input: PathLike, password: str | None = None) -> list[FormField]:
    """Campos del formulario en orden de aparición (los grupos de opciones se unen en un solo campo)."""
    with open_pdf(input, password, for_edit=False) as doc:
        return _fields(doc)


def _is_on(w: pymupdf.Widget) -> bool:
    v = w.field_value
    if v in (False, None, "", "Off"):
        return False
    return v is True or str(v) == str(w.on_state())


def _radio_groups(doc: pymupdf.Document) -> dict[str, list[tuple[int, str, bool]]]:
    """``{grupo: [(xref, etiqueta, marcado), ...]}``. Si los estados "on" se repiten, se numeran."""
    groups: dict[str, list] = {}
    for page in doc:
        for w in page.widgets() or []:
            if w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON and w.field_name:
                groups.setdefault(w.field_name, []).append((w.xref, str(w.on_state()), _is_on(w)))
    out = {}
    for name, items in groups.items():
        states = [st for _, st, _ in items]
        unique = len(set(states)) == len(states) and all(st not in ("None", "True", "") for st in states)
        out[name] = [(x, st if unique else f"Opción {k}", on) for k, (x, st, on) in enumerate(items, 1)]
    return out


def _fields(doc: pymupdf.Document) -> list[FormField]:
    out: dict[str, FormField] = {}
    radios = _radio_groups(doc)
    for page in doc:
        for w in page.widgets() or []:
            kind = KINDS.get(w.field_type)
            if kind is None or not w.field_name or w.field_name in out:
                continue
            ro = bool(w.field_flags & _READONLY)
            if kind == "opción":
                group = radios[w.field_name]
                chosen = next((label for _, label, on in group if on), "")
                out[w.field_name] = FormField(w.field_name, kind, chosen, page.number,
                                              options=[label for _, label, _ in group], readonly=ro,
                                              label=w.field_label or "")
            else:
                if kind == "casilla":
                    value = _is_on(w)
                else:
                    value = "" if w.field_value is None else str(w.field_value)
                out[w.field_name] = FormField(
                    w.field_name, kind, value, page.number,
                    options=[str(c[0]) if isinstance(c, (list, tuple)) else str(c) for c in (w.choice_values or [])],
                    readonly=ro, label=w.field_label or "",
                    multiline=bool(w.field_flags & pymupdf.PDF_TX_FIELD_IS_MULTILINE) if kind == "texto" else False,
                    max_length=w.text_maxlen or 0)
    return list(out.values())


def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "si", "sí", "x", "true", "yes", "on", "verdadero")


def fill_doc(doc: pymupdf.Document, values: Mapping[str, object], *, strict: bool = True) -> int:
    """Rellena un documento abierto. Devuelve cuántos campos cambiaron."""
    known = {f.name: f for f in _fields(doc)}
    unknown = [k for k in values if k not in known]
    if unknown and strict:
        raise ProcesadorPdfError("Campos que no existen en el formulario: " + ", ".join(unknown))
    changed: set[str] = set()
    radios = _radio_groups(doc)
    radio_target: dict[int, bool] = {}         # xref -> marcar
    radio_on: dict[str, str] = {}
    for name, v in values.items():
        f = known.get(name)
        if f is None or f.readonly or f.kind != "opción":
            continue
        if str(v) and str(v) not in f.options:
            raise ProcesadorPdfError(f"«{v}» no es una opción de «{name}»: {', '.join(f.options)}")
        for x, label, _ in radios[name]:
            radio_target[x] = label == str(v)
        changed.add(name)
    for page in doc:
        for w in page.widgets() or []:
            name = w.field_name
            if name not in values or name not in known:
                continue
            f, v = known[name], values[name]
            if f.readonly:
                continue
            if f.kind == "opción":
                if radio_target.get(w.xref):
                    on = str(w.on_state())
                    w.field_value = on
                    w.update()
                    radio_on[name] = on
                continue
            if f.kind == "casilla":
                w.field_value = w.on_state() if _truthy(v) else "Off"
            elif f.kind == "lista":
                if f.options and str(v) not in f.options and str(v) != "":
                    raise ProcesadorPdfError(f"«{v}» no es una opción de «{name}»: {', '.join(f.options)}")
                w.field_value = str(v)
            else:
                text = "" if v is None else str(v)
                if f.max_length and len(text) > f.max_length:
                    raise ProcesadorPdfError(f"«{name}» admite como máximo {f.max_length} caracteres")
                w.field_value = text
            w.update()
            changed.add(name)
    # Grupos de opciones: solo una marcada (las demás en /Off) y el valor del grupo coherente
    for name in {n for n, v in values.items() if known.get(n) and known[n].kind == "opción"}:
        on = radio_on.get(name)
        for x, _, _ in radios[name]:
            if not radio_target.get(x):
                doc.xref_set_key(x, "AS", "/Off")
            t, parent = doc.xref_get_key(x, "Parent")
            if t == "xref":
                doc.xref_set_key(int(parent.split()[0]), "V", f"/{on}" if on else "/Off")
    return len(changed)


def fill_form(input: PathLike, output: PathLike, values: Mapping[str, object], *, flatten: bool = False,
              strict: bool = True, password: str | None = None) -> tuple[Path, int]:
    """Diligencia el formulario con ``values = {nombre_campo: valor}``.

    - Casillas: ``True``/``False`` (o "sí", "x", "1"). Opciones: el nombre de la opción elegida.
    - ``flatten=True`` convierte los campos en contenido fijo (ya no se pueden editar).
    - ``strict``: error si un nombre no existe.

    Devuelve ``(ruta_salida, campos_cambiados)``.
    """
    doc = _open_for_filling(input, password)
    try:
        if not _fields(doc):
            raise ProcesadorPdfError("Este PDF no tiene campos de formulario para diligenciar")
        n = fill_doc(doc, values, strict=strict)
        if flatten:
            doc.bake(annots=False, widgets=True)
        return save_pdf(doc, output), n
    finally:
        doc.close()


def fill_from_csv(template: PathLike, csv_path: PathLike, output_dir: PathLike, *,
                  name_column: str | None = None, flatten: bool = False, delimiter: str | None = None,
                  password: str | None = None) -> list[Path]:
    """Genera un PDF diligenciado por cada fila del CSV (la primera fila son los nombres de los campos).

    ``name_column``: columna con el nombre del archivo de salida (si no, se numeran).
    Pensado para automatizar (V2): p. ej. una constancia por estudiante.
    """
    raw = Path(csv_path).read_text(encoding="utf-8-sig")
    if delimiter is None:
        delimiter = ";" if raw.splitlines()[0].count(";") > raw.splitlines()[0].count(",") else ","
    rows = list(csv.DictReader(raw.splitlines(), delimiter=delimiter))
    if not rows:
        raise ProcesadorPdfError("El CSV no tiene filas")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = {f.name for f in list_fields(template, password)}
    cols = [c for c in rows[0] if c != name_column]
    missing = [c for c in cols if c not in fields]
    if missing:
        raise ProcesadorPdfError("Columnas del CSV que no son campos del formulario: " + ", ".join(missing))
    made = []
    for i, row in enumerate(rows, 1):
        base = (row.get(name_column) or "").strip() if name_column else ""
        safe = "".join(ch for ch in base if ch.isalnum() or ch in " -_.").strip() or f"{Path(template).stem}_{i:03d}"
        values = {k: v for k, v in row.items() if k in fields}
        made.append(fill_form(template, out_dir / f"{safe}.pdf", values, flatten=flatten, password=password)[0])
    return made

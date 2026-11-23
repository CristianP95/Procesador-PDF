"""Pruebas de la v0.5: marca de agua, formularios y menú simplificado."""
import os

import pymupdf
import pytest

from pdftaller import core
from conftest import make_pdf, texts_of


# ---------------------------------------------------------------- marca de agua
def test_text_watermark_pages_and_rotation(tmp_path, pdf3):
    out, n = core.watermark(pdf3, tmp_path / "m.pdf", "CONFIDENCIAL", pages="1,3", opacity=0.3)
    assert n == 2
    t = texts_of(out)
    assert "CONFIDENCIAL" in t[0] and "CONFIDENCIAL" not in t[1] and "CONFIDENCIAL" in t[2]
    assert "Pagina uno" in t[0]                       # el contenido sigue ahí


def test_watermark_on_rotated_page_stays_inside(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.set_rotation(90)
    for pos in ("centro", "abajo"):
        core.apply_watermark(doc, text="BORRADOR", rotation=0, position=pos)
    bbox = pymupdf.Rect()
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            assert abs(line["dir"][0] - 0) < 0.01 or abs(abs(line["dir"][1]) - 1) < 0.01
            bbox |= line["bbox"]
    # dentro de la página (sin girar) y con el texto legible
    assert page.cropbox.contains(bbox)


def test_watermark_mosaic_behind_and_image(tmp_path, pdf3):
    out, _ = core.watermark(pdf3, tmp_path / "mo.pdf", "UMNG", position="mosaico", behind=True, color=(200, 0, 0))
    with pymupdf.open(out) as d:
        assert d[0].get_text().count("UMNG") >= 6
    img = tmp_path / "logo.png"
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 40), False)
    pix.clear_with(120)
    pix.save(img)
    out, n = core.watermark(pdf3, tmp_path / "im.pdf", image=img, opacity=0.5, scale=0.4)
    with pymupdf.open(out) as d:
        assert n == 3 and all(p.get_images() for p in d)
    with pytest.raises(core.PdfTallerError):
        core.watermark(pdf3, tmp_path / "x.pdf", "")
    with pytest.raises(core.PdfTallerError):
        core.watermark(pdf3, tmp_path / "x.pdf", "A", position="lado")


# ---------------------------------------------------------------- formularios
def _form(path):
    doc = pymupdf.open()
    page = doc.new_page()

    def add(t, name, rect, **kw):
        w = pymupdf.Widget()
        w.field_type, w.field_name, w.rect = t, name, pymupdf.Rect(rect)
        for k, v in kw.items():
            setattr(w, k, v)
        page.add_widget(w)
        return w

    add(pymupdf.PDF_WIDGET_TYPE_TEXT, "nombre", (100, 100, 300, 120), field_label="Nombre completo")
    add(pymupdf.PDF_WIDGET_TYPE_CHECKBOX, "acepta", (100, 140, 115, 155))
    add(pymupdf.PDF_WIDGET_TYPE_COMBOBOX, "programa", (100, 170, 300, 190), choice_values=["Ingeniería", "Derecho"])
    for cap, x in (("Diurna", 100), ("Nocturna", 150)):
        add(pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON, "jornada", (x, 200, x + 15, 215), field_value=cap)
    for w in page.widgets():
        if w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
            doc.xref_set_key(w.xref, "AS", "/Off")
    doc.save(path)
    return path


def test_list_and_fill_form(tmp_path):
    src = _form(tmp_path / "f.pdf")
    fields = {f.name: f for f in core.list_fields(src)}
    assert set(fields) == {"nombre", "acepta", "programa", "jornada"}
    assert fields["nombre"].label == "Nombre completo"
    assert fields["programa"].options == ["Ingeniería", "Derecho"]
    assert fields["jornada"].options == ["Diurna", "Nocturna"]
    out, n = core.fill_form(src, tmp_path / "o.pdf", {"nombre": "Ana Pérez", "acepta": "sí",
                                                       "programa": "Derecho", "jornada": "Nocturna"})
    assert n == 4
    got = {f.name: f.value for f in core.list_fields(out)}
    assert got == {"nombre": "Ana Pérez", "acepta": True, "programa": "Derecho", "jornada": "Nocturna"}
    out2, _ = core.fill_form(out, tmp_path / "o2.pdf", {"jornada": "Diurna", "acepta": False})
    got = {f.name: f.value for f in core.list_fields(out2)}
    assert got["jornada"] == "Diurna" and got["acepta"] is False
    with pytest.raises(core.PdfTallerError):
        core.fill_form(src, tmp_path / "x.pdf", {"no_existe": 1})
    with pytest.raises(core.PdfTallerError):
        core.fill_form(src, tmp_path / "x.pdf", {"programa": "Medicina"})


def test_flatten_and_csv_batch(tmp_path):
    src = _form(tmp_path / "f.pdf")
    flat, _ = core.fill_form(src, tmp_path / "flat.pdf", {"nombre": "Luis"}, flatten=True)
    with pymupdf.open(flat) as d:
        assert not list(d[0].widgets()) and "Luis" in d[0].get_text()
    csv = tmp_path / "datos.csv"
    csv.write_text("archivo;nombre;acepta;jornada\nana;Ana;si;Diurna\nluis;Luis;no;Nocturna\n", encoding="utf-8")
    made = core.fill_from_csv(src, csv, tmp_path / "lote", name_column="archivo")
    assert [p.name for p in made] == ["ana.pdf", "luis.pdf"]
    assert {f.name: f.value for f in core.list_fields(made[1])}["jornada"] == "Nocturna"
    with pytest.raises(core.PdfTallerError):
        core.fill_form(make_pdf(tmp_path / "sin.pdf", ["nada"]), tmp_path / "x.pdf", {})


def test_plain_name_for_ocr():
    assert core.recognize_text is core.ocr


# ---------------------------------------------------------------- interfaz
@pytest.fixture
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_menus_are_short_and_plain(qapp):
    from pdftaller.gui.main_window import MainWindow
    w = MainWindow()
    menus = {a.text().replace("&", ""): a.menu() for a in w.menuBar().actions()}
    assert list(menus) == ["Archivo", "Ordenar", "Optimizar", "Convertir", "Editar", "Seguridad"]
    for name, m in menus.items():
        top = [a for a in m.actions() if not a.isSeparator()]
        assert len(top) <= 8, (name, [a.text() for a in top])
    all_text = " ".join(a.text() for m in menus.values() for a in m.actions())
    assert "OCR" not in all_text and "Reconocer texto…" in all_text
    assert "Marca de agua…" in all_text and "Diligenciar formulario…" in all_text


def test_watermark_dialog_preview(qapp, tmp_path, pdf3):
    from pdftaller.gui.edit_dialogs import WatermarkDialog
    dlg = WatermarkDialog(pdf3, None, 0, 3)
    dlg._render()
    assert dlg.error.text() == "" and dlg.preview.pixmap() is not None and not dlg.preview.pixmap().isNull()

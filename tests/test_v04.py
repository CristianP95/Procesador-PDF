"""Pruebas de las correcciones de la v0.4 (núcleo y, si PySide6 está instalado, la interfaz)."""
import os

import pymupdf
import pytest

from procesador_pdf import core
from conftest import make_pdf, texts_of


# ---------------------------------------------------------------- proteger
def test_restrictions_without_open_password(tmp_path, pdf3):
    owner = core.generate_password()
    assert len(owner) == 16
    out = core.protect(pdf3, tmp_path / "r.pdf", "", owner, allow_print=True, allow_copy=False,
                       allow_modify=False, allow_annotate=False)
    assert not core.is_encrypted(out)                      # se abre sin contraseña…
    assert core.permissions(out) == {"imprimir": True, "copiar": False, "modificar": False, "comentar": False}
    assert all(core.permissions(out, owner).values())      # …y el propietario puede todo


def test_open_password_keeps_restrictions(tmp_path, pdf3):
    out = core.protect(pdf3, tmp_path / "p.pdf", "abrir", "dueno", allow_print=False)
    p = core.permissions(out, "abrir")
    assert not any(p.values())
    with pytest.raises(core.PasswordError):          # la app tampoco deja modificarlo
        core.reorder(out, tmp_path / "x.pdf", [1, 0, 2], password="abrir")


def test_protect_rejects_useless_restrictions(tmp_path, pdf3):
    with pytest.raises(core.ProcesadorPdfError):          # misma contraseña: no habría restricciones
        core.protect(pdf3, tmp_path / "a.pdf", "igual", "igual", allow_copy=False)
    with pytest.raises(core.ProcesadorPdfError):          # restricciones sin contraseña de permisos
        core.protect(pdf3, tmp_path / "b.pdf", "abrir", allow_print=False)
    # Solo contraseña de apertura: válido, sin restricciones
    out = core.protect(pdf3, tmp_path / "c.pdf", "abrir")
    assert core.is_encrypted(out) and all(core.permissions(out, "abrir").values())


# ---------------------------------------------------------------- censurar
def test_find_text_labeled_and_bad_regex(tmp_path):
    src = make_pdf(tmp_path / "s.pdf", ["Juan Perez 1234567", "nada"])
    hits = core.find_text_labeled(src, [r"\d{7}", "Juan"], regex=True)
    assert sorted(t for _, t in hits[0]) == ["1234567", "Juan"]
    with pytest.raises(core.ProcesadorPdfError):
        core.find_text(src, ["(sin cerrar"], regex=True)


# ---------------------------------------------------------------- firmas
def test_signature_trust_and_password_strength(tmp_path, pdf3):
    with pytest.raises(core.ProcesadorPdfError):
        core.create_certificate(tmp_path / "d.p12", "Débil", "clave123")
    p12 = core.create_certificate(tmp_path / "yo.p12", "Ana Prueba", "Clave-2026")
    signed = core.sign(pdf3, tmp_path / "s.pdf", p12, "Clave-2026", page=0, rect=(300, 650, 560, 760))
    st = core.verify_signatures(signed)[0]
    assert st.intact and st.covers_all and st.certified and not st.trusted
    assert len(st.fingerprint) == 95 and not st.timestamp
    cer, fp = core.export_public_certificate(p12, "Clave-2026", tmp_path / "yo.cer")
    assert fp == st.fingerprint and b"PRIVATE" not in cer.read_bytes()
    core.trust_certificate(core.signer_certificate(signed))
    assert core.verify_signatures(signed)[0].trusted
    assert core.untrust_certificate(fp) and not core.verify_signatures(signed)[0].trusted


def test_signature_with_handwritten_image(tmp_path, pdf3):
    img = tmp_path / "firma.png"
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 20), False)
    pix.clear_with(200)
    pix.save(img)
    p12 = core.create_certificate(tmp_path / "yo.p12", "Ana", "Clave-2026")
    signed = core.sign(pdf3, tmp_path / "s.pdf", p12, "Clave-2026", page=1, rect=(300, 600, 560, 760),
                       signature_image=img, lock=False)
    with pymupdf.open(signed) as d:
        assert d[1].get_images()
    st = core.verify_signatures(signed)[0]
    assert st.intact and st.covers_all and not st.certified


@pytest.mark.skipif(not os.environ.get("PROCESADOR_PDF_TEST_TSA"), reason="defina PROCESADOR_PDF_TEST_TSA=1 (usa internet)")
def test_signature_timestamp(tmp_path, pdf3):
    p12 = core.create_certificate(tmp_path / "yo.p12", "Ana", "Clave-2026")
    st = core.verify_signatures(core.sign(pdf3, tmp_path / "t.pdf", p12, "Clave-2026",
                                          timestamp_url=core.DEFAULT_TSA))[0]
    assert st.timestamp and st.timestamp_ok


# ---------------------------------------------------------------- optimizar
def _photo_pdf(tmp_path):
    import random
    rnd = random.Random(1)                               # "foto" con ruido: no se comprime sola
    w = h = 1200
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, bytes(rnd.randrange(256) for _ in range(w * h * 3)), False)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(50, 50, 350, 350), pixmap=pix)
    page.insert_text((72, 400), "Foto de prueba")
    doc.save(tmp_path / "foto.pdf")
    return tmp_path / "foto.pdf"


def test_analyze_and_custom_compression(tmp_path):
    src = _photo_pdf(tmp_path)
    a = core.analyze(src)
    assert a.image_count == 1 and a.images > a.total * 0.5 and a.max_image_dpi > 250
    assert a.recommendation() == "media" and "Imágenes" in a.message()
    sizes = core.estimate_compression(src)
    assert sizes["alta"] <= sizes["media"] <= sizes["baja"] <= src.stat().st_size
    rep = core.compress(src, tmp_path / "c.pdf", dpi=72, quality=40, strip=True)
    assert rep.after < sizes["media"]
    with pytest.raises(core.ProcesadorPdfError):
        core.compress(src, tmp_path / "x.pdf", dpi=5)


@pytest.mark.skipif(core.find_tessdata() is None, reason="Tesseract no instalado")
def test_ocr_keeps_original_page(tmp_path):
    from test_v03 import _scan
    scan = _scan(tmp_path)
    rep = core.ocr(scan, tmp_path / "o.pdf", language="spa")
    assert rep.pages_ocr == 1 and rep.words >= 3
    with pymupdf.open(rep.path) as d, pymupdf.open(scan) as s:
        assert "mundo" in d[0].get_text().lower()
        # la imagen original sigue siendo la misma (no se volvió a rasterizar)
        assert d.xref_stream(d[0].get_images()[0][0]) == s.xref_stream(s[0].get_images()[0][0])
        assert d[0].search_for("mundo")


# ---------------------------------------------------------------- interfaz (sin pantalla)
@pytest.fixture
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _order(tab):
    from PySide6.QtCore import Qt
    return [tab.pages.item(i).data(Qt.UserRole) for i in range(tab.pages.count())]


def test_gui_drag_backwards(qapp, tmp_path):
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from procesador_pdf.gui.document_tab import DocumentTab
    src = make_pdf(tmp_path / "d.pdf", [f"P{i}" for i in range(8)])
    tab = DocumentTab(src)
    tab.resize(900, 700)
    tab.show()
    qapp.processEvents()
    lst, vp = tab.pages, tab.pages.viewport()

    def ev(kind, pos, btn, btns):
        QApplication.sendEvent(vp, QMouseEvent(kind, QPointF(pos), QPointF(vp.mapToGlobal(pos)), btn, btns,
                                               Qt.NoModifier))

    def rect(r):
        return lst.visualRect(lst.model().index(r, 0))

    start, target = rect(3).center(), QPoint(rect(0).center().x(), rect(0).top() + 3)
    if lst._horizontal(0):
        target = QPoint(rect(0).left() + 3, rect(0).center().y())
    ev(QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton)
    for k in range(1, 9):
        ev(QEvent.MouseMove, start + (target - start) * (k / 8), Qt.NoButton, Qt.LeftButton)
    ev(QEvent.MouseButtonRelease, target, Qt.LeftButton, Qt.NoButton)
    assert _order(tab)[:2] == [3, 0]
    assert tab.undo() and _order(tab) == list(range(8))


def test_gui_censor_and_undo_after_save(qapp, tmp_path):
    from PySide6.QtCore import QRectF
    from procesador_pdf.gui.document_tab import DocumentTab
    src = make_pdf(tmp_path / "d.pdf", ["Juan Perez 123", "Otra Juan Perez"])
    tab = DocumentTab(src)
    tab.show()
    assert tab.show_censor_panel()
    found, new, _ = tab.search_and_mark(["Juan Perez"], False)
    assert (found, new) == (2, 2)
    tab.btn_redact.setChecked(True)
    tab._on_rect_drawn(QRectF(10, 10, 50, 50))
    assert tab.censor.list.count() == 3
    tab.censor.result_view.setChecked(True)          # vista previa del resultado final
    assert "resultado final" in tab.page_label.text()
    tab.remove_marks([tab.marks[0]])
    assert tab.censor.list.count() == 2
    tab.save()
    assert "Juan" not in texts_of(src)[1] and tab.marks == []
    assert tab.undo_text() == "aplicar censura"
    assert tab.undo() and tab.modified and len(tab.marks) == 2   # vuelve a antes de guardar
    tab.save()
    assert "Juan" not in texts_of(src)[1]

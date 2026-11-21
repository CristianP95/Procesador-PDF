import pymupdf
import pytest

from pdftaller import core
from conftest import make_pdf, texts_of


def test_protect_restrictions_apply(tmp_path, pdf3):
    # Abrir sin contraseña, pero con restricciones
    out = core.protect(pdf3, tmp_path / "r.pdf", "", "dueno", allow_print=False, allow_copy=False)
    assert not core.is_encrypted(out)
    perms = core.permissions(out)
    assert perms == {"imprimir": False, "copiar": False, "modificar": False, "comentar": False}
    assert core.permissions(out, "dueno")["imprimir"]
    # La app respeta las restricciones
    with pytest.raises(core.PasswordError):
        core.reorder(out, tmp_path / "x.pdf", [1, 0, 2])
    core.reorder(out, tmp_path / "ok.pdf", [1, 0, 2], password="dueno")


def test_protect_user_and_owner(tmp_path, pdf3):
    out = core.protect(pdf3, tmp_path / "p.pdf", "abrir", "dueno", allow_print=True)
    assert core.is_encrypted(out)
    p = core.permissions(out, "abrir")
    assert p["imprimir"] and not p["copiar"] and not p["modificar"]
    with pytest.raises(core.PdfTallerError):
        core.protect(pdf3, tmp_path / "z.pdf", "", "")


def _scan(tmp_path):
    """PDF 'escaneado': solo una imagen con texto."""
    src = make_pdf(tmp_path / "t.pdf", ["Hola mundo escaneado"])
    with pymupdf.open(src) as d:
        pix = d[0].get_pixmap(dpi=200)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(tmp_path / "scan.pdf")
    return tmp_path / "scan.pdf"


def test_compress_and_repair(tmp_path):
    scan = _scan(tmp_path)
    rep = core.compress(scan, tmp_path / "c.pdf", "alta")
    assert rep.after <= rep.before and rep.path.exists()
    # Archivo dañado: truncar la tabla xref
    data = (tmp_path / "c.pdf").read_bytes()
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(data.replace(b"startxref", b"startxrXf"))
    r = core.repair(bad, tmp_path / "fixed.pdf")
    assert r.pages == 1 and r.path.exists()


@pytest.mark.skipif(core.find_tessdata() is None, reason="Tesseract no instalado")
def test_ocr(tmp_path):
    scan = _scan(tmp_path)
    assert texts_of(scan) == [""]
    rep = core.ocr(scan, tmp_path / "o.pdf", language="spa")
    assert rep.pages_ocr == 1
    with pymupdf.open(rep.path) as d:
        assert "mundo" in d[0].get_text().lower()
        assert abs(d[0].rect.width - 595) < 2


def test_digital_signature(tmp_path, pdf3):
    p12 = core.create_certificate(tmp_path / "yo.p12", "Cristian Prueba", "Clave-123", organization="UMNG")
    signed = core.sign(pdf3, tmp_path / "s.pdf", p12, "Clave-123", reason="Aprobado",
                       page=0, rect=(72, 600, 272, 680))
    st = core.verify_signatures(signed)
    assert len(st) == 1 and st[0].intact and st[0].covers_all and "Cristian" in st[0].signer
    # Cambio posterior (guardado incremental con una anotación): se detecta
    with pymupdf.open(signed) as d:
        d[1].add_text_annot((100, 100), "cambio")
        d.save(tmp_path / "mod.pdf")
    st2 = core.verify_signatures(tmp_path / "mod.pdf")
    assert not (st2 and st2[0].intact and st2[0].covers_all)
    # Alterar bytes del contenido firmado
    data = bytearray(signed.read_bytes())
    i = data.find(b"/MediaBox")
    data[i + 12] = ord("9") if data[i + 12] != ord("9") else ord("8")
    (tmp_path / "t.pdf").write_bytes(bytes(data))
    assert not core.verify_signatures(tmp_path / "t.pdf")[0].intact
    with pytest.raises(core.PasswordError):
        core.sign(pdf3, tmp_path / "x.pdf", p12, "mala")

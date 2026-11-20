import pymupdf

from pdftaller import core
from conftest import make_pdf, texts_of


def _png(path, color=(255, 0, 0)):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 20), False)
    pix.set_rect(pix.irect, color)
    pix.save(path)
    return path


def test_certify_and_verify(tmp_path, pdf3):
    cert = core.certify(pdf3, author="Cristian")
    assert cert.name == "tres.pdf.sha256.json"
    assert core.verify(pdf3).ok
    core.reorder(pdf3, pdf3, [1, 0, 2])  # alterar
    res = core.verify(pdf3)
    assert not res.ok and "MODIFICADO" in res.message()
    assert core.verify(pdf3, expected_hash=core.file_hash(pdf3).upper()).ok


def test_insert_signature(tmp_path, pdf3):
    img = _png(tmp_path / "firma.png")
    out = core.insert_signature(pdf3, tmp_path / "f.pdf", 1, (100, 600, 300, 700), img)
    with pymupdf.open(out) as d:
        assert len(d[1].get_image_info()) == 1 and not d[0].get_image_info()


def test_images_to_pdf(tmp_path):
    imgs = [_png(tmp_path / "a.png"), _png(tmp_path / "b.png", (0, 0, 255))]
    out = core.images_to_pdf(imgs, tmp_path / "i.pdf", page_size="A4")
    with pymupdf.open(out) as d:
        assert d.page_count == 2 and d[0].rect.width > d[0].rect.height  # imagen apaisada -> hoja apaisada


def test_redact_area(tmp_path):
    src = make_pdf(tmp_path / "s.pdf", ["Dato secreto"])
    with pymupdf.open(src) as d:
        r = d[0].search_for("secreto")[0]
    out, n = core.redact(src, tmp_path / "c.pdf", areas={0: [tuple(r)]})
    assert n == 1 and "secreto" not in texts_of(out)[0] and "Dato" in texts_of(out)[0]

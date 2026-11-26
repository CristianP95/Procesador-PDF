import pymupdf
import pytest


def make_pdf(path, texts):
    doc = pymupdf.open()
    for t in texts:
        page = doc.new_page()
        page.insert_text((72, 72), t, fontsize=14)
    doc.save(path)
    doc.close()
    return path


def texts_of(path, password=None):
    with pymupdf.open(path) as doc:
        if password:
            doc.authenticate(password)
        return [p.get_text().strip() for p in doc]


@pytest.fixture
def pdf3(tmp_path):
    return make_pdf(tmp_path / "tres.pdf", ["Pagina uno", "Pagina dos", "Pagina tres"])


@pytest.fixture(autouse=True)
def _lista_confianza_aislada(tmp_path, monkeypatch):
    """Las pruebas no tocan la lista de certificados de confianza del usuario."""
    monkeypatch.setenv("PROCESADOR_PDF_TRUST_DIR", str(tmp_path / "confianza"))

import pytest

from procesador_pdf import core
from conftest import make_pdf, texts_of


def test_protect_and_unlock(tmp_path, pdf3):
    prot = core.protect(pdf3, tmp_path / "p.pdf", "secreto")
    assert core.is_encrypted(prot)
    with pytest.raises(core.PasswordError):
        core.unlock(prot, tmp_path / "x.pdf", "mala")
    free = core.unlock(prot, tmp_path / "libre.pdf", "secreto")
    assert not core.is_encrypted(free)
    assert texts_of(free)[0] == "Pagina uno"


def test_operations_on_protected_input(tmp_path, pdf3):
    prot = core.protect(pdf3, tmp_path / "p.pdf", "k")
    out = core.merge([prot], tmp_path / "m.pdf", passwords=["k"])
    assert len(texts_of(out)) == 3


def test_compare(tmp_path, pdf3):
    b = make_pdf(tmp_path / "b.pdf", ["Pagina uno", "Pagina DOS cambiada"])
    res = core.compare(pdf3, b, visual=True)
    assert not res.identical
    assert not res.pages[0].changed
    assert res.pages[1].removed == ["Pagina dos"] and res.pages[1].added == ["Pagina DOS cambiada"]
    assert res.pages[2].removed == ["Pagina tres"]
    assert core.compare(pdf3, pdf3, visual=True).identical
    assert "Página 2" in res.summary()


def test_redact_removes_text(tmp_path):
    src = make_pdf(tmp_path / "s.pdf", ["Cedula 1234567 de Juan", "Sin datos"])
    out, n = core.redact(src, tmp_path / "c.pdf", ["Juan"])
    assert n == 1
    assert "Juan" not in texts_of(out)[0]
    out, n = core.redact(src, tmp_path / "c2.pdf", [r"\d{7}"], regex=True)
    assert n == 1 and "1234567" not in texts_of(out)[0]
    assert core.find_text(src, ["datos"]) .keys() == {1}


def test_edits_keep_protection(tmp_path, pdf3):
    prot = core.protect(pdf3, tmp_path / "p.pdf", "k")
    out = core.reorder(prot, tmp_path / "r.pdf", [1, 0], password="k")
    assert core.is_encrypted(out)
    assert texts_of(out, "k") == ["Pagina dos", "Pagina uno"]


def test_unlock_requires_owner_password(tmp_path, pdf3):
    prot = core.protect(pdf3, tmp_path / "p.pdf", "usuario", "dueno")
    with pytest.raises(core.PasswordError):
        core.unlock(prot, tmp_path / "x.pdf", "usuario")
    assert not core.is_encrypted(core.unlock(prot, tmp_path / "ok.pdf", "dueno"))
    # Solo restricciones (abre sin contraseña)
    import pymupdf
    with pymupdf.open(pdf3) as d:
        d.save(tmp_path / "r.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="dueno", user_pw="", permissions=0)
    with pytest.raises(core.PasswordError):
        core.unlock(tmp_path / "r.pdf", tmp_path / "x2.pdf", "mala")
    core.unlock(tmp_path / "r.pdf", tmp_path / "ok2.pdf", "dueno")

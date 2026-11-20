import pytest

from pdftaller import core
from conftest import make_pdf, texts_of


def test_parse_ranges():
    assert core.parse_page_ranges("1-3, 5", 6) == [0, 1, 2, 4]
    assert core.parse_page_ranges("4-", 5) == [3, 4]
    assert core.parse_page_ranges("-2", 5) == [0, 1]
    assert core.parse_page_ranges("3-1", 5) == [2, 1, 0]
    with pytest.raises(core.PageRangeError):
        core.parse_page_ranges("9", 5)
    with pytest.raises(core.PageRangeError):
        core.parse_page_ranges("a-b", 5)


def test_merge_with_ranges(tmp_path, pdf3):
    other = make_pdf(tmp_path / "b.pdf", ["Otro A", "Otro B"])
    out = core.merge([pdf3, other], tmp_path / "u.pdf", page_ranges=["3", None])
    assert texts_of(out) == ["Pagina tres", "Otro A", "Otro B"]


def test_split_every_and_ranges(tmp_path, pdf3):
    files = core.split(pdf3, tmp_path / "e", every=2)
    assert [len(texts_of(f)) for f in files] == [2, 1]
    files = core.split(pdf3, tmp_path / "r", ranges="1; 2-3")
    assert [texts_of(f) for f in files] == [["Pagina uno"], ["Pagina dos", "Pagina tres"]]


def test_reorder_delete_rotate(tmp_path, pdf3):
    out = core.reorder(pdf3, tmp_path / "o.pdf", [2, 0, 1])
    assert texts_of(out) == ["Pagina tres", "Pagina uno", "Pagina dos"]
    out = core.delete_pages(pdf3, tmp_path / "d.pdf", [1])
    assert texts_of(out) == ["Pagina uno", "Pagina tres"]
    out = core.rotate_pages(pdf3, tmp_path / "rot.pdf", [0], 90)
    import pymupdf
    with pymupdf.open(out) as d:
        assert [p.rotation for p in d] == [90, 0, 0]


def test_overwrite_same_file(tmp_path, pdf3):
    core.reorder(pdf3, pdf3, [1, 0])
    assert texts_of(pdf3) == ["Pagina dos", "Pagina uno"]

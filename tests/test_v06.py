"""Pruebas de la v0.6: rueda del ratón entre páginas, logo y ventana Acerca de."""
import os

import pytest

from conftest import make_pdf


@pytest.fixture
def qapp():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _wheel(widget, dy):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication
    pos = QPointF(widget.width() / 2, widget.height() / 2)
    ev = QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, dy),
                     Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)
    qapp_process()


def qapp_process():
    from PySide6.QtWidgets import QApplication
    for _ in range(3):
        QApplication.processEvents()


def test_wheel_moves_to_next_and_previous_page(qapp, tmp_path):
    from procesador_pdf.gui.document_tab import DocumentTab
    tab = DocumentTab(make_pdf(tmp_path / "d.pdf", ["uno", "dos", "tres"]))
    tab.resize(900, 600)
    tab.show()
    qapp_process()
    tab.set_zoom(2.0)                      # página más alta que la vista: hay que desplazarse
    qapp_process()
    vp, bar = tab.scroll.viewport(), tab.scroll.verticalScrollBar()
    assert bar.maximum() > 0 and tab.pages.currentRow() == 0
    _wheel(vp, -120)                       # en medio de la página: solo desplaza
    assert tab.pages.currentRow() == 0
    bar.setValue(bar.maximum())
    _wheel(vp, -120)                       # en el borde inferior: página siguiente
    assert tab.pages.currentRow() == 1 and bar.value() == bar.minimum()
    _wheel(vp, 120)                        # en el borde superior: página anterior
    assert tab.pages.currentRow() == 0 and bar.value() == bar.maximum()
    assert tab.step_page(-1) is False      # no hay página antes de la primera


def test_about_dialog_and_logo(qapp):
    from procesador_pdf import __version__, branding
    from procesador_pdf.gui.about import AboutDialog, app_icon
    from procesador_pdf.gui.main_window import MainWindow
    assert branding.asset("app.png").exists() and branding.asset("autor.png").exists() and not app_icon().isNull()
    assert "## [0.6.0]" in branding.changelog()
    dlg = AboutDialog()
    assert branding.VERSION == __version__ and dlg.tabs.count() == 2
    w = MainWindow()
    assert branding.APP_NAME in w.windowTitle() and not w.windowIcon().isNull()
    menus = [a.text().replace("&", "") for a in w.menuBar().actions()]
    assert menus[-1] == "Ayuda"

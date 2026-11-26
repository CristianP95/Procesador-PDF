"""Ventana «Acerca de»: identidad, versión, componentes e historial de versiones."""
from __future__ import annotations

import platform
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QTabWidget, QTextBrowser, QVBoxLayout

from procesador_pdf import branding


def app_icon() -> QIcon:
    return QIcon(str(branding.asset("app.png")))


def logo(height: int, name: str = "app.png") -> QLabel:
    """Logo de la aplicación (``app.png``) o del autor (``autor.png``) escalado a ``height``."""
    lab = QLabel()
    pm = QPixmap(str(branding.asset(name)))
    if not pm.isNull():
        lab.setPixmap(pm.scaledToHeight(height, Qt.SmoothTransformation))
    return lab


def _components() -> list[tuple[str, str]]:
    out = [("Python", platform.python_version())]
    from importlib import metadata
    for name, dist in (("PyMuPDF", "pymupdf"), ("PySide6 (Qt)", "PySide6"),
                       ("pyHanko", "pyhanko"), ("cryptography", "cryptography")):
        try:
            out.append((name, metadata.version(dist)))
        except metadata.PackageNotFoundError:
            out.append((name, "no instalado"))
    try:
        from procesador_pdf import core
        td = core.find_tessdata()
        langs = ", ".join(core.ocr_languages()) if td else "sin datos"
        out.append(("Tesseract (reconocer texto)", langs))
    except Exception:
        pass
    return out


class AboutDialog(QDialog):
    def __init__(self, parent=None, tab: int = 0):
        super().__init__(parent)
        self.setWindowTitle(f"Acerca de {branding.APP_NAME}")
        self.resize(620, 520)

        head = QHBoxLayout()
        head.addWidget(logo(96))
        info = QLabel(
            f"<h2 style='margin:0'>{escape(branding.APP_NAME)}</h2>"
            f"<p style='margin:2px 0'>Versión {escape(branding.VERSION)}</p>"
            f"<p>{escape(branding.DESCRIPTION)}</p>")
        info.setWordWrap(True)
        head.addWidget(info, 1)

        about = QTextBrowser()
        about.setOpenExternalLinks(True)
        rows = "".join(f"<tr><td>{escape(n)}</td><td>{escape(v)}</td></tr>" for n, v in _components())
        repo = (f"<p><b>Código fuente:</b> <a href='{escape(branding.REPOSITORY)}'>{escape(branding.REPOSITORY)}</a></p>"
                if branding.REPOSITORY else "")
        author_logo = branding.asset("autor.png")
        about.setHtml(
            (f"<p><img src='{author_logo.as_uri()}' height='48'></p>" if author_logo.exists() else "")
            + f"<p><b>Desarrollo:</b> {escape(branding.AUTHOR)}</p>"
            f"<p><b>Licencia:</b> {escape(branding.LICENSE)}. Es software libre: puede usarlo, estudiarlo, "
            "modificarlo y compartirlo. Si distribuye una versión modificada (también como servicio en red), "
            "debe publicar su código bajo la misma licencia.</p>"
            f"{repo}"
            "<p><b>Privacidad:</b> los documentos se procesan solo en este equipo. Únicamente el sello de "
            "tiempo de la firma digital, si se activa, se conecta a internet.</p>"
            "<p><b>Componentes:</b></p>"
            f"<table cellpadding='3'>{rows}</table>")

        history = QTextBrowser()
        history.setOpenExternalLinks(True)
        history.setMarkdown(branding.changelog() or "Sin historial disponible.")

        self.tabs = QTabWidget()
        self.tabs.addTab(about, "Información")
        self.tabs.addTab(history, "Historial de versiones")
        self.tabs.setCurrentIndex(tab)

        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.button(QDialogButtonBox.Close).setText("Cerrar")
        box.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(head)
        lay.addWidget(self.tabs, 1)
        lay.addWidget(box)

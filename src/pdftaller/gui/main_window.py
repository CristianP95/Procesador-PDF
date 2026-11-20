"""Ventana principal: una pestaña por documento y menús Ordenar / Seguridad."""
from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog, QInputDialog, QLabel, QMainWindow, QMessageBox, QStackedWidget, QTabWidget, QToolBar,
)

from pdftaller import core

from .dialogs import PDF_FILTER, CompareDialog, MergeDialog, ProtectDialog, RedactDialog, SplitDialog, ask_password
from .document_tab import DocumentTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Taller")
        self.resize(1100, 750)
        self.setAcceptDrops(True)

        self.tabs = QTabWidget(tabsClosable=True, movable=True, documentMode=True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._update_actions)
        welcome = QLabel("Abra un PDF (Ctrl+O) o arrástrelo aquí para empezar.\n\n"
                         "Ordenar: unir, dividir, reordenar · Seguridad: proteger, desbloquear, comparar, censurar")
        welcome.setAlignment(Qt.AlignCenter)
        self.stack = QStackedWidget()
        self.stack.addWidget(welcome)
        self.stack.addWidget(self.tabs)
        self.setCentralWidget(self.stack)

        self._doc_actions: list[QAction] = []
        self._build_menus()
        self._update_actions()
        self.statusBar().showMessage("Listo")

    # ------------------------------------------------------------ menús
    def _act(self, menu, text, slot, shortcut=None, needs_doc=True, toolbar=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        menu.addAction(a)
        if toolbar is not None:
            toolbar.addAction(a)
        if needs_doc:
            self._doc_actions.append(a)
        return a

    def _build_menus(self):
        bar = self.menuBar()
        tb = QToolBar("Principal")
        tb.setMovable(False)
        self.addToolBar(tb)

        m = bar.addMenu("&Archivo")
        self._act(m, "Abrir…", self.open_dialog, QKeySequence.Open, needs_doc=False, toolbar=tb)
        self._act(m, "Guardar", self.save, QKeySequence.Save, toolbar=tb)
        self._act(m, "Guardar como…", self.save_as, QKeySequence.SaveAs)
        self._act(m, "Cerrar pestaña", lambda: self.close_tab(self.tabs.currentIndex()), QKeySequence.Close)
        m.addSeparator()
        self._act(m, "Salir", self.close, QKeySequence.Quit, needs_doc=False)
        tb.addSeparator()

        m = bar.addMenu("&Ordenar")
        self._act(m, "Unir…", self.merge, needs_doc=False, toolbar=tb)
        self._act(m, "Dividir…", self.split, toolbar=tb)
        self._act(m, "Extraer páginas seleccionadas…", self.extract)
        m.addSeparator()
        self._act(m, "Rotar a la izquierda", lambda: self._rotate(-90), "Ctrl+L")
        self._act(m, "Rotar a la derecha", lambda: self._rotate(90), "Ctrl+R")
        self._act(m, "Eliminar páginas seleccionadas", self.delete_pages, QKeySequence.Delete)
        tb.addSeparator()

        m = bar.addMenu("&Seguridad")
        self._act(m, "Proteger…", self.protect, toolbar=tb)
        self._act(m, "Desbloquear…", self.unlock, toolbar=tb)
        self._act(m, "Comparar…", self.compare, toolbar=tb)
        self._act(m, "Censurar…", self.redact, toolbar=tb)

    def _update_actions(self, *_):
        has = self.current() is not None
        for a in self._doc_actions:
            a.setEnabled(has)
        self.stack.setCurrentIndex(1 if self.tabs.count() else 0)

    # ------------------------------------------------------------ pestañas
    def current(self) -> DocumentTab | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, DocumentTab) else None

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Abrir PDF", "", PDF_FILTER)
        for p in paths:
            self.open_file(p)

    def open_file(self, path: str | Path, password: str | None = None) -> DocumentTab | None:
        path = Path(path)
        for i in range(self.tabs.count()):
            t = self.tabs.widget(i)
            if t.path.resolve() == path.resolve():
                t.password = password or t.password
                t.reload()
                self.tabs.setCurrentIndex(i)
                return t
        try:
            if password is None and core.is_encrypted(path):
                password = ask_password(self, path.name)
                if password is None:
                    return None
            core.page_count(path, password)  # valida archivo y contraseña
            tab = DocumentTab(path, password)
        except (core.PdfTallerError, RuntimeError, pymupdf.FileDataError, OSError) as exc:
            QMessageBox.critical(self, "Abrir", str(exc))
            return None
        idx = self.tabs.addTab(tab, tab.title())
        self.tabs.setTabToolTip(idx, str(path))
        tab.modified_changed.connect(lambda _=None, t=tab: self._retitle(t))
        self.tabs.setCurrentIndex(idx)
        self._update_actions()
        return tab

    def _retitle(self, tab: DocumentTab):
        i = self.tabs.indexOf(tab)
        if i >= 0:
            self.tabs.setTabText(i, tab.title())
            self.tabs.setTabToolTip(i, str(tab.path))

    def close_tab(self, index: int):
        tab = self.tabs.widget(index)
        if tab is None:
            return
        if tab.modified:
            r = QMessageBox.question(self, "Cerrar", f"«{tab.path.name}» tiene cambios sin guardar. ¿Guardarlos?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel or (r == QMessageBox.Save and not self.save()):
                return
        self.tabs.removeTab(index)
        tab.deleteLater()
        self._update_actions()

    def closeEvent(self, event):
        while self.tabs.count():
            n = self.tabs.count()
            self.tabs.setCurrentIndex(0)
            self.close_tab(0)
            if self.tabs.count() == n:
                event.ignore()
                return
        event.accept()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.toLocalFile().lower().endswith(".pdf"):
                self.open_file(url.toLocalFile())

    # ------------------------------------------------------------ ayudas
    def _run(self, title: str, fn, *args, **kwargs):
        """Ejecuta una operación del núcleo mostrando los errores al usuario."""
        self.statusBar().showMessage(f"{title}…")
        try:
            return fn(*args, **kwargs)
        except (core.PdfTallerError, RuntimeError, OSError) as exc:
            QMessageBox.critical(self, title, str(exc))
            return None
        finally:
            self.statusBar().clearMessage()

    def _ask_output(self, title: str, suggested: Path) -> str | None:
        p, _ = QFileDialog.getSaveFileName(self, title, str(suggested), PDF_FILTER)
        if not p:
            return None
        return p if p.lower().endswith(".pdf") else p + ".pdf"

    # ------------------------------------------------------------ archivo
    def save(self) -> bool:
        tab = self.current()
        if tab is None:
            return False
        if self._run("Guardar", tab.save) is None:
            return False
        self._retitle(tab)
        self.statusBar().showMessage(f"Guardado: {tab.path}", 5000)
        return True

    def save_as(self):
        tab = self.current()
        out = tab and self._ask_output("Guardar como", tab.path)
        if out and self._run("Guardar como", tab.save, out):
            self._retitle(tab)

    # ------------------------------------------------------------ ordenar
    def merge(self):
        tab = self.current()
        initial = [str(self.tabs.widget(i).path) for i in range(self.tabs.count())]
        dlg = MergeDialog(initial, self)
        if not dlg.exec() or len(dlg.paths()) < 1:
            return
        paths = dlg.paths()
        pw = {str(self.tabs.widget(i).path): self.tabs.widget(i).password for i in range(self.tabs.count())}
        passwords = []
        for p in paths:
            if p not in pw and core.is_encrypted(p):
                pw[p] = ask_password(self, Path(p).name)
            passwords.append(pw.get(p))
        base = Path(paths[0]).with_name("unido.pdf") if not tab else tab.path.with_name("unido.pdf")
        out = self._ask_output("Guardar PDF unido", base)
        if out and self._run("Unir", core.merge, paths, out, passwords=passwords):
            self.open_file(out)

    def split(self):
        tab = self.current()
        dlg = SplitDialog(tab.pages.count(), str(tab.path.parent / f"{tab.path.stem}_partes"), self)
        if not dlg.exec():
            return
        src = tab.materialize()
        files = self._run("Dividir", core.split, src, dlg.folder.text(), prefix=tab.path.stem,
                          password=tab.password, **dlg.options())
        if files:
            QMessageBox.information(self, "Dividir", f"Se crearon {len(files)} archivos en:\n{dlg.folder.text()}")

    def extract(self):
        tab = self.current()
        spec = tab.selected_page_spec()
        spec, ok = QInputDialog.getText(self, "Extraer páginas", "Páginas (p. ej. 1-3, 5):", text=spec)
        if not ok or not spec.strip():
            return
        out = self._ask_output("Guardar páginas extraídas", tab.path.with_name(f"{tab.path.stem}_extracto.pdf"))
        if out and self._run("Extraer", core.extract_pages, tab.materialize(), out, spec, password=tab.password):
            self.open_file(out, tab.password)

    def _rotate(self, deg: int):
        if not self.current().rotate_selected(deg):
            self.statusBar().showMessage("Seleccione una o más páginas", 3000)

    def delete_pages(self):
        n = self.current().delete_selected()
        if n < 0:
            QMessageBox.warning(self, "Eliminar", "No se pueden eliminar todas las páginas.")
        elif n == 0:
            self.statusBar().showMessage("Seleccione una o más páginas", 3000)

    # ------------------------------------------------------------ seguridad
    def protect(self):
        tab = self.current()
        dlg = ProtectDialog(self)
        if not dlg.exec():
            return
        out = self._ask_output("Guardar PDF protegido", tab.path.with_name(f"{tab.path.stem}_protegido.pdf"))
        opts = dlg.options()
        if out and self._run("Proteger", core.protect, tab.materialize(), out, password=tab.password, **opts):
            self.open_file(out, opts["user_password"])

    def unlock(self):
        tab = self.current()
        with pymupdf.open(tab.path) as d:
            protected = bool(d.metadata.get("encryption"))
        if not protected:
            QMessageBox.information(self, "Desbloquear", "Este documento no está protegido.")
            return
        out = self._ask_output("Guardar PDF desbloqueado", tab.path.with_name(f"{tab.path.stem}_desbloqueado.pdf"))
        if not out:
            return
        src, pw = tab.materialize(), tab.password
        while True:
            try:
                if pw:
                    core.unlock(src, out, pw)
                    break
            except core.PasswordError:
                pass
            except core.PdfTallerError as exc:
                QMessageBox.critical(self, "Desbloquear", str(exc))
                return
            pw = ask_password(self, f"{tab.path.name} (contraseña de propietario)")
            if pw is None:
                return
        self.open_file(out)

    def compare(self):
        tab = self.current()
        CompareDialog(tab.materialize(), tab.password, self).exec()

    def redact(self):
        tab = self.current()
        src = tab.materialize()
        dlg = RedactDialog(src, tab.password, self)
        if not dlg.exec():
            return
        out = self._ask_output("Guardar PDF censurado", tab.path.with_name(f"{tab.path.stem}_censurado.pdf"))
        if not out:
            return
        res = self._run("Censurar", core.redact, src, out, dlg.term_list(), regex=dlg.regex.isChecked(),
                        remove_metadata=dlg.meta.isChecked(), password=tab.password)
        if res:
            path, count = res
            self.statusBar().showMessage(f"{count} zona(s) censurada(s)", 6000)
            self.open_file(path, tab.password)

"""Ventana principal: una pestaña por documento y menús Ordenar / Seguridad."""
from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox, QStackedWidget, QTabWidget, QToolBar,
)

from pdftaller import core

from .dialogs import (IMG_FILTER, PDF_FILTER, CertifyDialog, CompareDialog, CompressDialog, OcrDialog,
                      SignaturesDialog, SignDialog, TrustDialog, VerifyDialog, _info_copy)
from .dialogs import MergeDialog, ProtectDialog, SplitDialog, ask_password
from .document_tab import DocumentTab
from .worker import run_busy


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        from pdftaller import __version__
        self.setWindowTitle(f"PDF Taller {__version__}")
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
    SHORT = {"Insertar firma (imagen)…": "Firma (imagen)", "Reconocer texto (OCR)…": "OCR",
             "Censurar (texto y zonas)…": "Censurar", "Deshacer": "↶ Deshacer", "Rehacer": "↷ Rehacer",
             "Certificar con huella (hash)…": "Certificar", "Firmar digitalmente (certificado)…": "Firma digital",
             "Desbloquear…": "Desbloquear", "Comprimir…": "Comprimir"}

    def _act(self, menu, text, slot, shortcut=None, needs_doc=True, toolbar=None):
        a = QAction(text, self)
        a.setIconText(self.SHORT.get(text, text.rstrip("…")))
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
        self._act(m, "Crear PDF desde imágenes…", self.images_to_pdf, needs_doc=False)
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
        m.addSeparator()
        self._act(m, "Mover a la izquierda", lambda: self.current().move_selected("izquierda"), "Alt+Left")
        self._act(m, "Mover a la derecha", lambda: self.current().move_selected("derecha"), "Alt+Right")
        self._act(m, "Mover al inicio", lambda: self.current().move_selected("inicio"), "Alt+Home")
        self._act(m, "Mover al final", lambda: self.current().move_selected("final"), "Alt+End")
        self._act(m, "Mover a la posición…", self.move_to_position)
        tb.addSeparator()

        m = bar.addMenu("&Editar")
        self.a_undo = self._act(m, "Deshacer", self.undo, QKeySequence.Undo, toolbar=tb)
        self.a_redo = self._act(m, "Rehacer", self.redo, "Ctrl+Y", toolbar=tb)
        self.a_redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        for a in (self.a_undo, self.a_redo):
            a.setShortcutContext(Qt.ApplicationShortcut)
        tb.addSeparator()
        m.addSeparator()
        self._act(m, "Insertar firma (imagen)…", self.start_signature, toolbar=tb)
        self._act(m, "Cambiar imagen de firma…", lambda: self.current().request_signature_image())
        tb.addSeparator()

        m = bar.addMenu("O&ptimizar")
        self._act(m, "Analizar tamaño…", self.analyze)
        self._act(m, "Comprimir…", self.compress, toolbar=tb)
        self._act(m, "Reparar…", self.repair)
        self._act(m, "Reconocer texto (OCR)…", self.ocr, toolbar=tb)
        tb.addSeparator()

        m = bar.addMenu("&Seguridad")
        self._act(m, "Proteger…", self.protect, toolbar=tb)
        self._act(m, "Desbloquear…", self.unlock)
        self._act(m, "Comparar…", self.compare, toolbar=tb)
        self._act(m, "Censurar (texto y zonas)…", self.redact, "Ctrl+Shift+C", toolbar=tb)
        self._act(m, "Censurar por texto…", self.redact)
        self._act(m, "Censurar zona (dibujar recuadro)", self.start_area_redaction)
        m.addSeparator()
        self._act(m, "Certificar con huella (hash)…", self.certify, toolbar=tb)
        self._act(m, "Verificar integridad…", self.verify, needs_doc=False)
        m.addSeparator()
        self._act(m, "Firmar digitalmente (certificado)…", self.digital_sign, toolbar=tb)
        self._act(m, "Verificar firmas digitales…", self.verify_signatures)
        self._act(m, "Certificados de confianza…", lambda: TrustDialog(self).exec(), needs_doc=False)

    def _update_actions(self, *_):
        has = self.current() is not None
        for a in self._doc_actions:
            a.setEnabled(has)
        self.stack.setCurrentIndex(1 if self.tabs.count() else 0)
        self._update_history()

    def _update_history(self):
        tab = self.current()
        u = tab.undo_text() if tab else ""
        r = tab.redo_text() if tab else ""
        self.a_undo.setEnabled(bool(u))
        self.a_redo.setEnabled(bool(r))
        self.a_undo.setText(f"Deshacer {u}" if u else "Deshacer")
        self.a_redo.setText(f"Rehacer {r}" if r else "Rehacer")
        self.a_undo.setIconText("↶ Deshacer")
        self.a_redo.setIconText("↷ Rehacer")
        self.a_undo.setToolTip(f"Deshacer: {u} (Ctrl+Z)" if u else "Nada que deshacer")
        self.a_redo.setToolTip(f"Rehacer: {r} (Ctrl+Y)" if r else "Nada que rehacer")

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
        tab.status.connect(lambda msg: self.statusBar().showMessage(msg, 5000))
        tab.pages.customContextMenuRequested.connect(lambda pos, t=tab: self._page_menu(t, pos))
        tab.history_changed.connect(lambda t=tab: t is self.current() and self._update_history())
        tab.apply_censor_requested.connect(lambda t=tab: self._apply_censor(t))
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

    def _run_bg(self, title: str, text: str, fn, *args, **kwargs):
        """Como ``_run`` pero en segundo plano, con ventana de progreso (no congela la ventana)."""
        try:
            return run_busy(self, title, text, fn, *args, **kwargs)
        except (core.PdfTallerError, RuntimeError, OSError) as exc:
            QMessageBox.critical(self, title, str(exc))
            return None

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
        if tab.read_only:
            QMessageBox.warning(self, "Guardar", "El documento tiene restricciones de modificación.\n"
                                "Use Seguridad → Desbloquear con la contraseña de permisos.")
            return False
        if tab.signed and tab.modified:
            r = QMessageBox.warning(self, "Guardar", "El documento está firmado digitalmente: al guardar cambios "
                                    "la firma dejará de ser válida.\n¿Continuar?",
                                    QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if r != QMessageBox.Yes:
                return False
        if tab.has_redactions:
            r = QMessageBox.question(
                self, "Guardar",
                "La censura es permanente: el texto bajo las zonas se elimina del archivo.\n\n"
                "¿Guardar en un archivo NUEVO (recomendado)?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
            if r == QMessageBox.Cancel:
                return False
            if r == QMessageBox.Yes:
                out = self._ask_output("Guardar PDF censurado", tab.path.with_name(f"{tab.path.stem}_censurado.pdf"))
                if not out or self._run("Guardar", tab.save, out) is None:
                    return False
                self._retitle(tab)
                return True
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
        if n == -2:
            return
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
        if not (out and self._run("Proteger", core.protect, tab.materialize(), out, password=tab.password, **opts)):
            return
        user = opts["user_password"]
        p = core.permissions(out, user or None)
        lines = ["Documento protegido (AES-256).", "",
                 ("Con la contraseña de apertura" if user else "Al abrirlo (sin contraseña)") + " se podrá:"]
        lines += [f"   {'✔' if v else '✘'} {k}" for k, v in p.items()]
        owner = opts["owner_password"]
        if owner and owner != user:
            lines += ["", "Con la contraseña de permisos: todo permitido (solo para usted)."]
        if dlg.generated:
            lines += ["", "Contraseña de permisos generada (guárdela; sin ella no podrá desbloquear):", owner]
        lines += ["", "Nota: Adobe Reader y PDF Taller aplican estas restricciones; los visores de los "
                  "navegadores pueden ignorar algunas."]
        if dlg.generated:
            _info_copy(self, "Proteger", "\n".join(lines), owner)
        else:
            QMessageBox.information(self, "Proteger", "\n".join(lines))
        self.open_file(out, user or None)

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
        if tab.show_censor_panel():
            self.statusBar().showMessage("Busque textos o dibuje zonas; revise la lista y la vista previa. "
                                         "Nada se borra hasta aplicar.", 10000)

    def _apply_censor(self, tab: DocumentTab):
        if tab is not self.current():
            return
        tab.scrub_metadata = tab.censor.meta.isChecked()
        if self.save():
            self.statusBar().showMessage("Censura aplicada. Ctrl+Z vuelve a la versión anterior.", 8000)

    # ------------------------------------------------------------ menú contextual
    def _page_menu(self, tab: DocumentTab, pos):
        it = tab.pages.itemAt(pos)
        if it is not None and not it.isSelected():
            tab.pages.clearSelection()
            it.setSelected(True)
            tab.pages.setCurrentItem(it)
        if not tab.pages.selectedItems():
            return
        n = len(tab.pages.selectedItems())
        m = QMenu(self)
        m.addSection(f"{n} página(s) seleccionada(s)")
        m.addAction("Rotar a la izquierda", lambda: tab.rotate_selected(-90))
        m.addAction("Rotar a la derecha", lambda: tab.rotate_selected(90))
        m.addAction("Girar 180°", lambda: tab.rotate_selected(180))
        m.addSeparator()
        m.addAction("Mover a la izquierda", lambda: tab.move_selected("izquierda"))
        m.addAction("Mover a la derecha", lambda: tab.move_selected("derecha"))
        m.addAction("Mover al inicio", lambda: tab.move_selected("inicio"))
        m.addAction("Mover al final", lambda: tab.move_selected("final"))
        m.addAction("Mover a la posición…", self.move_to_position)
        m.addSeparator()
        m.addAction("Extraer a un PDF nuevo…", self.extract)
        m.addAction("Censurar zona en esta página", self.start_area_redaction)
        m.addAction("Insertar firma en esta página", self.start_signature)
        m.addSeparator()
        m.addAction("Eliminar", self.delete_pages)
        m.exec(tab.pages.viewport().mapToGlobal(pos))

    def move_to_position(self):
        tab = self.current()
        rows = tab.pages.selected_rows()
        if not rows:
            self.statusBar().showMessage("Seleccione una o más páginas", 3000)
            return
        n, ok = QInputDialog.getInt(self, "Mover páginas", f"Nueva posición (1 a {tab.pages.count()}):",
                                    rows[0] + 1, 1, tab.pages.count())
        if ok:
            tab.pages.move_rows(rows, n - 1, final=True)

    def start_area_redaction(self):
        tab = self.current()
        if tab.show_censor_panel(draw=True):
            self.statusBar().showMessage("Dibuje recuadros sobre la vista previa. Se aplican al pulsar "
                                         "«Aplicar censura».", 8000)

    def start_signature(self):
        tab = self.current()
        tab.btn_sign.setChecked(True)
        if tab.btn_sign.isChecked():
            self.statusBar().showMessage("Dibuje el recuadro donde irá la firma. Guarde para aplicarla.", 8000)

    # ------------------------------------------------------------ convertir / integridad
    def images_to_pdf(self):
        imgs, _ = QFileDialog.getOpenFileNames(self, "Elegir imágenes (en orden)", "", IMG_FILTER)
        if not imgs:
            return
        size, ok = QInputDialog.getItem(self, "Tamaño de página", "Tamaño de cada hoja:",
                                        ["Igual a la imagen", "A4", "Carta (letter)"], 0, False)
        if not ok:
            return
        page_size = {"A4": "A4", "Carta (letter)": "letter"}.get(size)
        out = self._ask_output("Guardar PDF", Path(imgs[0]).with_name("imagenes.pdf"))
        if out and self._run("Imágenes a PDF", core.images_to_pdf, imgs, out, page_size=page_size, margin=18 if page_size else 0):
            self.open_file(out)

    def certify(self):
        tab = self.current()
        if tab.modified:
            QMessageBox.information(self, "Certificar", "Guarde primero los cambios: se certifica el archivo guardado.")
            return
        CertifyDialog(tab.path, self).exec()

    def verify(self):
        tab = self.current()
        VerifyDialog(tab.path if tab else None, self).exec()

    # ------------------------------------------------------------ deshacer
    def undo(self):
        tab = self.current()
        label = tab.undo_text()
        if tab.undo():
            self.statusBar().showMessage(f"Deshecho: {label}", 3000)
        else:
            self.statusBar().showMessage("Nada que deshacer", 2000)
        self._update_history()

    def redo(self):
        tab = self.current()
        label = tab.redo_text()
        if tab.redo():
            self.statusBar().showMessage(f"Rehecho: {label}", 3000)
        else:
            self.statusBar().showMessage("Nada que rehacer", 2000)
        self._update_history()

    # ------------------------------------------------------------ optimizar
    def analyze(self):
        tab = self.current()
        a = self._run("Analizar", core.analyze, tab.materialize(), tab.password)
        if a:
            QMessageBox.information(self, f"Analizar «{tab.path.name}»", a.message())

    def compress(self):
        tab = self.current()
        src = tab.materialize()
        dlg = CompressDialog(src, tab.password, self)
        if not dlg.exec():
            return
        out = self._ask_output("Guardar PDF comprimido", tab.path.with_name(f"{tab.path.stem}_comprimido.pdf"))
        opts = dlg.options()
        level = opts.pop("level")
        rep = out and self._run_bg("Comprimir", "Comprimiendo…", core.compress, src, out, level, **opts)
        if rep:
            QMessageBox.information(self, "Comprimir", rep.message())
            self.open_file(rep.path, tab.password)

    def repair(self):
        tab = self.current()
        out = self._ask_output("Guardar PDF reparado", tab.path.with_name(f"{tab.path.stem}_reparado.pdf"))
        rep = out and self._run_bg("Reparar", "Revisando y reparando…", core.repair, tab.path, out,
                                   password=tab.password)
        if rep:
            QMessageBox.information(self, "Reparar", rep.message())
            self.open_file(rep.path, tab.password)

    def ocr(self):
        tab = self.current()
        langs = core.ocr_languages()
        if not langs:
            QMessageBox.warning(
                self, "OCR", "No se encontraron los datos de reconocimiento de texto (Tesseract).\n\n"
                "Instale Tesseract para Windows con el idioma español:\n"
                "https://github.com/UB-Mannheim/tesseract/wiki\n\n"
                "o copie la carpeta 'tessdata' junto a PDFTaller.exe.")
            return
        dlg = OcrDialog(langs, self)
        if not dlg.exec():
            return
        out = self._ask_output("Guardar PDF con texto", tab.path.with_name(f"{tab.path.stem}_ocr.pdf"))
        if not out:
            return
        rep = self._run_bg("OCR", "Reconociendo texto…", core.ocr, tab.materialize(), out,
                           language=dlg.lang.currentData(), dpi=dlg.dpi.value(),
                           only_without_text=dlg.only.isChecked(), keep_original=dlg.keep.isChecked(),
                           password=tab.password, progress=True)
        if rep:
            QMessageBox.information(self, "OCR", rep.message())
            self.open_file(rep.path, tab.password)

    # ------------------------------------------------------------ firma digital
    def digital_sign(self):
        tab = self.current()
        if tab.read_only:
            return tab.can_edit()
        row = tab.pages.currentRow()
        dlg = SignDialog(f"la página {row + 1}", self)
        if not dlg.exec():
            return
        out = self._ask_output("Guardar PDF firmado", tab.path.with_name(f"{tab.path.stem}_firmado.pdf"))
        if not out:
            return
        src = tab.materialize()
        page = rect = None
        if dlg.visible.isChecked():
            import pymupdf
            with pymupdf.open(src) as d:
                r = d[row].rect
            page, rect = row, (r.width - 250, r.height - 100, r.width - 30, r.height - 30)
        opts = dlg.options()
        if page is not None and opts["signature_image"]:
            rect = (rect[0], rect[1] - 60, rect[2], rect[3])     # más alto para la imagen manuscrita
        res = self._run_bg("Firmar", "Firmando" + (" y obteniendo el sello de tiempo…" if opts["timestamp_url"]
                                                     else "…"),
                           core.sign, src, out, dlg.cert.text(), dlg.pw.text(), page=page, rect=rect, **opts)
        if res:
            st = core.verify_signatures(res)[-1]
            QMessageBox.information(self, "Firmar", "Documento firmado digitalmente y verificado.\n\n"
                                    + "\n".join(st.details) + f"\n\nHuella del certificado:\n{st.fingerprint}")
            self.open_file(res)

    def verify_signatures(self):
        SignaturesDialog(self.current().path, self).exec()

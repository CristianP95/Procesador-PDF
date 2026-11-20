"""Diálogos de las operaciones de Ordenar y Seguridad."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QSpinBox, QTextBrowser, QVBoxLayout, QWidget,
)

from html import escape

from PySide6.QtGui import QGuiApplication

from pdftaller import core

PDF_FILTER = "Documentos PDF (*.pdf)"
IMG_FILTER = "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)"


def _buttons(dialog: QDialog, ok_text: str = "Aceptar") -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.button(QDialogButtonBox.Ok).setText(ok_text)
    box.button(QDialogButtonBox.Cancel).setText("Cancelar")
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class MergeDialog(QDialog):
    """Lista de archivos a unir, con orden editable."""

    def __init__(self, initial: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unir PDF")
        self.resize(560, 380)
        self.files = QListWidget()
        self.files.setDragDropMode(QListWidget.InternalMove)
        self.files.addItems(initial)
        side = QVBoxLayout()
        for text, slot in [("Agregar…", self._add), ("Quitar", self._remove),
                           ("Subir", lambda: self._move(-1)), ("Bajar", lambda: self._move(1))]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            side.addWidget(b)
        side.addStretch()
        row = QHBoxLayout()
        row.addWidget(self.files)
        row.addLayout(side)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Los archivos se unirán en este orden (puede arrastrarlos):"))
        lay.addLayout(row)
        lay.addWidget(_buttons(self, "Unir"))

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Agregar PDF", "", PDF_FILTER)
        self.files.addItems(paths)

    def _remove(self):
        for it in self.files.selectedItems():
            self.files.takeItem(self.files.row(it))

    def _move(self, delta: int):
        row = self.files.currentRow()
        new = row + delta
        if row < 0 or not 0 <= new < self.files.count():
            return
        it = self.files.takeItem(row)
        self.files.insertItem(new, it)
        self.files.setCurrentRow(new)

    def paths(self) -> list[str]:
        return [self.files.item(i).text() for i in range(self.files.count())]


class SplitDialog(QDialog):
    def __init__(self, page_count: int, default_dir: str, parent=None):
        super().__init__(parent)
        self.page_count = page_count
        self.setWindowTitle("Dividir PDF")
        self.setMinimumWidth(520)
        self.r_ranges = QRadioButton("Por rangos de páginas")
        self.r_every = QRadioButton("En partes iguales: un archivo cada")
        self.r_ranges.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.r_ranges)
        grp.addButton(self.r_every)
        half = max(1, page_count // 2)
        self.ranges = QLineEdit(f"1-{half}; {half + 1}-{page_count}" if page_count > 1 else "1")
        self.ranges.setToolTip("Cada grupo separado por ; será un archivo. Ej.: 1-13; 14-31")
        self.every = QSpinBox()
        self.every.setRange(1, max(1, page_count))
        self.every.setValue(max(1, page_count))
        self.every.setSuffix(" página(s)")
        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.folder = QLineEdit(default_dir)
        browse = QPushButton("…")
        browse.clicked.connect(self._browse)
        frow = QHBoxLayout()
        frow.addWidget(self.folder)
        frow.addWidget(browse)

        form = QFormLayout()
        form.addRow(self.r_ranges, self.ranges)
        form.addRow("", QLabel("Separe cada archivo con punto y coma (;). Ej.: 1-13; 14-31"))
        form.addRow(self.r_every, self.every)
        form.addRow("Carpeta de salida:", _wrap(frow))
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"El documento tiene {page_count} páginas."))
        lay.addLayout(form)
        lay.addWidget(self.preview)
        lay.addWidget(_buttons(self, "Dividir"))
        for w in (self.r_ranges, self.r_every):
            w.toggled.connect(self._update)
        self.ranges.textChanged.connect(self._update)
        self.ranges.textEdited.connect(lambda: self.r_ranges.setChecked(True))
        self.every.valueChanged.connect(lambda: (self.r_every.setChecked(True), self._update()))
        self._update()

    def _groups(self) -> list[list[int]]:
        if self.r_every.isChecked():
            n, k = self.page_count, self.every.value()
            return [list(range(s, min(s + k, n))) for s in range(0, n, k)]
        return core.parse_range_groups(self.ranges.text(), self.page_count)

    def _update(self, *_):
        try:
            groups = self._groups()
        except core.PdfTallerError as exc:
            self.preview.setText(f"<span style='color:#b00'>⚠ {escape(str(exc))}</span>")
            return
        desc = [f"{g[0] + 1}-{g[-1] + 1}" if len(g) > 1 else f"{g[0] + 1}" for g in groups[:8]]
        more = f" … y {len(groups) - 8} más" if len(groups) > 8 else ""
        self.preview.setText(f"Se crearán <b>{len(groups)} archivo(s)</b>: páginas " + ", ".join(desc) + more)

    def accept(self):
        try:
            self._groups()
        except core.PdfTallerError as exc:
            QMessageBox.warning(self, "Dividir", str(exc))
            return
        super().accept()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta de salida", self.folder.text())
        if d:
            self.folder.setText(d)

    def options(self) -> dict:
        if self.r_every.isChecked():
            return {"every": self.every.value()}
        return {"ranges": self.ranges.text()}


class ProtectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Proteger PDF")
        self.user = QLineEdit(echoMode=QLineEdit.Password)
        self.confirm = QLineEdit(echoMode=QLineEdit.Password)
        self.owner = QLineEdit(echoMode=QLineEdit.Password)
        self.owner.setPlaceholderText("Opcional (por defecto, la misma)")
        self.c_print = QCheckBox("Permitir imprimir")
        self.c_print.setChecked(True)
        self.c_copy = QCheckBox("Permitir copiar texto")
        self.c_modify = QCheckBox("Permitir modificar")
        self.c_annot = QCheckBox("Permitir comentarios y formularios")
        form = QFormLayout(self)
        form.addRow("Contraseña para abrir:", self.user)
        form.addRow("Repetir contraseña:", self.confirm)
        form.addRow("Contraseña de propietario:", self.owner)
        for c in (self.c_print, self.c_copy, self.c_modify, self.c_annot):
            form.addRow(c)
        form.addRow(QLabel("Cifrado: AES-256"))
        form.addRow(_buttons(self, "Proteger"))

    def accept(self):
        if not self.user.text():
            QMessageBox.warning(self, "Proteger", "Escriba una contraseña.")
            return
        if self.user.text() != self.confirm.text():
            QMessageBox.warning(self, "Proteger", "Las contraseñas no coinciden.")
            return
        super().accept()

    def options(self) -> dict:
        return dict(
            user_password=self.user.text(),
            owner_password=self.owner.text() or None,
            allow_print=self.c_print.isChecked(),
            allow_copy=self.c_copy.isChecked(),
            allow_modify=self.c_modify.isChecked(),
            allow_annotate=self.c_annot.isChecked(),
        )


class RedactDialog(QDialog):
    def __init__(self, source: Path, password: str | None, parent=None):
        super().__init__(parent)
        self.source, self.password = source, password
        self.setWindowTitle("Censurar PDF")
        self.resize(480, 360)
        self.terms = QPlainTextEdit()
        self.terms.setPlaceholderText("Un texto por línea, p. ej.:\nJuan Pérez\n1234567890")
        self.regex = QCheckBox("Interpretar como expresiones regulares (p. ej. \\d{10})")
        self.meta = QCheckBox("Borrar también los metadatos (autor, título…)")
        self.meta.setChecked(True)
        self.result = QLabel()
        preview = QPushButton("Buscar coincidencias")
        preview.clicked.connect(self._preview)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Textos a censurar. Se eliminan del archivo, no solo se tapan:"))
        lay.addWidget(self.terms)
        lay.addWidget(self.regex)
        lay.addWidget(self.meta)
        row = QHBoxLayout()
        row.addWidget(preview)
        row.addWidget(self.result, 1)
        lay.addLayout(row)
        lay.addWidget(_buttons(self, "Censurar"))

    def term_list(self) -> list[str]:
        return [t.strip() for t in self.terms.toPlainText().splitlines() if t.strip()]

    def _preview(self):
        try:
            hits = core.find_text(self.source, self.term_list(), regex=self.regex.isChecked(), password=self.password)
        except Exception as exc:
            self.result.setText(f"Error: {exc}")
            return
        total = sum(len(v) for v in hits.values())
        pages = ", ".join(str(p + 1) for p in sorted(hits)) or "ninguna"
        self.result.setText(f"{total} coincidencia(s) · páginas: {pages}")

    def accept(self):
        if not self.term_list():
            QMessageBox.warning(self, "Censurar", "Escriba al menos un texto.")
            return
        super().accept()


class CompareDialog(QDialog):
    def __init__(self, source: Path, password: str | None, parent=None):
        super().__init__(parent)
        self.source, self.password = source, password
        self.setWindowTitle(f"Comparar «{source.name}»")
        self.resize(760, 560)
        self.other = QLineEdit()
        self.other.returnPressed.connect(self._run)
        browse = QPushButton("Elegir…")
        browse.clicked.connect(self._browse)
        self.visual = QCheckBox("Comparar también la imagen de cada página (detecta cambios en firmas, sellos, imágenes)")
        run = QPushButton("Comparar")
        run.clicked.connect(self._run)
        self.output = QTextBrowser()
        row = QHBoxLayout()
        row.addWidget(QLabel("Documento B:"))
        row.addWidget(self.other, 1)
        row.addWidget(browse)
        row.addWidget(run)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Documento A: {source}"))
        lay.addLayout(row)
        lay.addWidget(self.visual)
        lay.addWidget(self.output, 1)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.button(QDialogButtonBox.Close).setText("Cerrar")
        close.rejected.connect(self.reject)
        lay.addWidget(close)

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Documento B", "", PDF_FILTER)
        if p:
            self.other.setText(p)
            self._run()          # compara de inmediato

    def _run(self):
        b = self.other.text().strip()
        if not b:
            return
        pw_b = None
        try:
            if core.is_encrypted(b):
                pw_b = ask_password(self, Path(b).name)
                if pw_b is None:
                    return
            res = core.compare(self.source, b, visual=self.visual.isChecked(),
                               password_a=self.password, password_b=pw_b)
            self.output.setHtml(_compare_html(res))
        except core.PdfTallerError as exc:
            self.output.setPlainText(f"Error: {exc}")


def _compare_html(res: core.CompareResult) -> str:
    if res.identical:
        return "<h3 style='color:#1a7f37'>✔ Los documentos son iguales.</h3>"
    changed = [p for p in res.pages if p.changed]
    h = [f"<h3 style='color:#b35900'>Se encontraron diferencias en {len(changed)} página(s)</h3>",
         f"<p>Documento A: {res.pages_a} páginas · Documento B: {res.pages_b} páginas</p>"]
    for p in changed:
        h.append(f"<h4>Página {p.page}</h4><table cellspacing=0 cellpadding=3 width='100%'>")
        for t in p.removed:
            h.append(f"<tr><td style='background:#ffe1e1;color:#8a0000'>− Solo en A: {escape(t)}</td></tr>")
        for t in p.added:
            h.append(f"<tr><td style='background:#dcf5dc;color:#0a5c0a'>+ Solo en B: {escape(t)}</td></tr>")
        if p.visual_change and not (p.added or p.removed):
            h.append(f"<tr><td style='background:#fff4d6'>Cambio visual en {p.visual_change:.1%} de la página "
                     "(imagen, firma o sello)</td></tr>")
        h.append("</table>")
    return "".join(h)


class CertifyDialog(QDialog):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path
        self.setWindowTitle("Certificar documento")
        self.setMinimumWidth(560)
        self.author = QLineEdit()
        self.note = QLineEdit()
        self.note.setPlaceholderText("Ej.: Acta firmada del 20/11/2026")
        self.result = QLineEdit(readOnly=True)
        copy = QPushButton("Copiar huella")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.result.text()))
        form = QFormLayout(self)
        form.addRow(QLabel(
            "Se calcula la huella SHA-256 del archivo y se guarda en un certificado junto a él "
            f"(<i>{escape(core.certificate_path(path).name)}</i>). Si alguien modifica el PDF, "
            "la huella cambia y la verificación lo detecta. Comparta la huella por un canal aparte "
            "(correo, acta) para poder auditar después."))
        form.addRow("Responsable:", self.author)
        form.addRow("Nota:", self.note)
        form.addRow("Huella SHA-256:", self.result)
        form.addRow("", copy)
        box = _buttons(self, "Certificar")
        box.button(QDialogButtonBox.Cancel).setText("Cerrar")
        form.addRow(box)

    def accept(self):
        try:
            cert = core.certify(self.path, self.author.text(), self.note.text())
        except (core.PdfTallerError, OSError) as exc:
            QMessageBox.critical(self, "Certificar", str(exc))
            return
        self.result.setText(core.file_hash(self.path))
        QMessageBox.information(self, "Certificar", f"Certificado guardado en:\n{cert}")


class VerifyDialog(QDialog):
    def __init__(self, path: Path | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Verificar integridad")
        self.setMinimumWidth(600)
        self.doc = QLineEdit(str(path) if path else "")
        b1 = QPushButton("…")
        b1.clicked.connect(lambda: self._pick(self.doc, PDF_FILTER))
        self.cert = QLineEdit()
        self.cert.setPlaceholderText("Automático: <documento>.pdf.sha256.json")
        b2 = QPushButton("…")
        b2.clicked.connect(lambda: self._pick(self.cert, "Certificados (*.json)"))
        self.hash = QLineEdit()
        self.hash.setPlaceholderText("O pegue aquí la huella SHA-256 recibida")
        self.result = QLabel()
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form = QFormLayout(self)
        form.addRow("Documento:", _row(self.doc, b1))
        form.addRow("Certificado:", _row(self.cert, b2))
        form.addRow("Huella:", self.hash)
        form.addRow(self.result)
        box = _buttons(self, "Verificar")
        box.button(QDialogButtonBox.Cancel).setText("Cerrar")
        form.addRow(box)

    def _pick(self, edit, flt):
        p, _ = QFileDialog.getOpenFileName(self, "Elegir archivo", "", flt)
        if p:
            edit.setText(p)

    def accept(self):
        try:
            res = core.verify(self.doc.text(), self.cert.text() or None, self.hash.text() or None)
        except (core.PdfTallerError, OSError) as exc:
            self.result.setText(f"<span style='color:#b00'>{escape(str(exc))}</span>")
            return
        color = "#1a7f37" if res.ok else "#b00"
        self.result.setText(f"<b style='color:{color}'>{escape(res.message()).replace(chr(10), '<br>')}</b>")


def ask_password(parent: QWidget, name: str) -> str | None:
    from PySide6.QtWidgets import QInputDialog
    pw, ok = QInputDialog.getText(parent, "Documento protegido",
                                  f"«{name}» está protegido. Contraseña:", QLineEdit.Password)
    return pw if ok else None


def _row(*widgets) -> QWidget:
    lay = QHBoxLayout()
    for w in widgets:
        lay.addWidget(w)
    return _wrap(lay)


def _wrap(layout) -> QWidget:
    w = QWidget()
    layout.setContentsMargins(0, 0, 0, 0)
    w.setLayout(layout)
    return w

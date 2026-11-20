"""Diálogos de las operaciones de Ordenar y Seguridad."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from pdftaller import core

PDF_FILTER = "Documentos PDF (*.pdf)"


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
        self.setWindowTitle("Dividir PDF")
        self.r_every = QRadioButton("Un archivo cada")
        self.r_ranges = QRadioButton("Por rangos (separe archivos con ;)")
        self.r_every.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.r_every)
        grp.addButton(self.r_ranges)
        self.every = QSpinBox()
        self.every.setRange(1, max(1, page_count))
        self.every.setSuffix(" página(s)")
        self.ranges = QLineEdit()
        self.ranges.setPlaceholderText(f"Ej.: 1-3; 4-6; 7-{page_count}")
        self.folder = QLineEdit(default_dir)
        browse = QPushButton("…")
        browse.clicked.connect(self._browse)
        frow = QHBoxLayout()
        frow.addWidget(self.folder)
        frow.addWidget(browse)

        form = QFormLayout()
        form.addRow(self.r_every, self.every)
        form.addRow(self.r_ranges, self.ranges)
        form.addRow("Carpeta de salida:", _wrap(frow))
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"El documento tiene {page_count} páginas."))
        lay.addLayout(form)
        lay.addWidget(_buttons(self, "Dividir"))

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
        self.resize(640, 480)
        self.other = QLineEdit()
        browse = QPushButton("Elegir…")
        browse.clicked.connect(self._browse)
        self.visual = QCheckBox("Comparar también la imagen de cada página (más lento)")
        run = QPushButton("Comparar")
        run.clicked.connect(self._run)
        self.output = QPlainTextEdit(readOnly=True)
        row = QHBoxLayout()
        row.addWidget(QLabel("Documento B:"))
        row.addWidget(self.other, 1)
        row.addWidget(browse)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Documento A: {source}"))
        lay.addLayout(row)
        lay.addWidget(self.visual)
        lay.addWidget(run)
        lay.addWidget(self.output, 1)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.button(QDialogButtonBox.Close).setText("Cerrar")
        close.rejected.connect(self.reject)
        lay.addWidget(close)

    def _browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Documento B", "", PDF_FILTER)
        if p:
            self.other.setText(p)

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
            self.output.setPlainText(res.summary())
        except core.PdfTallerError as exc:
            self.output.setPlainText(f"Error: {exc}")


def ask_password(parent: QWidget, name: str) -> str | None:
    from PySide6.QtWidgets import QInputDialog
    pw, ok = QInputDialog.getText(parent, "Documento protegido",
                                  f"«{name}» está protegido. Contraseña:", QLineEdit.Password)
    return pw if ok else None


def _wrap(layout) -> QWidget:
    w = QWidget()
    layout.setContentsMargins(0, 0, 0, 0)
    w.setLayout(layout)
    return w

"""Diálogos de Editar: marca de agua y diligenciar formularios."""
from __future__ import annotations

from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from procesador_pdf import core

IMG_FILTER = "Imágenes (*.png *.jpg *.jpeg *.bmp)"


def _pix_to_qpixmap(pix: pymupdf.Pixmap) -> QPixmap:
    return QPixmap.fromImage(QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy())


class WatermarkDialog(QDialog):
    """Marca de agua de texto o imagen, con vista previa en vivo de la página actual."""

    POS = {"centro": "En el centro", "mosaico": "Repetida en toda la hoja", "arriba": "Arriba", "abajo": "Abajo"}

    def __init__(self, source: Path, password: str | None, page: int, page_count: int, parent=None):
        super().__init__(parent)
        self.source, self.password, self.page = source, password, page
        self.setWindowTitle("Marca de agua")
        self.resize(860, 560)
        self.color = QColor("#808080")

        self.r_text = QRadioButton("Texto")
        self.r_image = QRadioButton("Imagen (logo, sello)")
        self.r_text.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.r_text)
        grp.addButton(self.r_image)
        self.text = QPlainTextEdit("CONFIDENCIAL")
        self.text.setMaximumHeight(60)
        self.image = QLineEdit()
        self.image.setPlaceholderText("Archivo de imagen")
        pick = QPushButton("…")
        pick.clicked.connect(self._pick)
        self.btn_color = QPushButton()
        self.btn_color.clicked.connect(self._pick_color)
        self._paint_color()
        self.size = QSpinBox()
        self.size.setRange(0, 300)
        self.size.setSpecialValueText("Automático")
        self.size.setSuffix(" pt")
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(5, 100)
        self.opacity.setValue(25)
        self.opacity_label = QLabel()
        self.rotation = QSpinBox()
        self.rotation.setRange(-180, 180)
        self.rotation.setValue(45)
        self.rotation.setSuffix("°")
        self.position = QComboBox()
        for k, v in self.POS.items():
            self.position.addItem(v, k)
        self.scale = QSpinBox()
        self.scale.setRange(5, 100)
        self.scale.setValue(50)
        self.scale.setSuffix(" % del ancho")
        self.behind = QCheckBox("Detrás del contenido (no tapa el texto)")
        self.pages = QLineEdit()
        self.pages.setPlaceholderText(f"Todas (1-{page_count}); o p. ej. 1-3, 5")

        form = QFormLayout()
        form.addRow(self.r_text, self.text)
        form.addRow(self.r_image, _row(self.image, pick))
        form.addRow("Color:", self.btn_color)
        form.addRow("Tamaño de letra:", self.size)
        form.addRow("Opacidad:", _row(self.opacity, self.opacity_label))
        form.addRow("Giro:", self.rotation)
        form.addRow("Posición:", self.position)
        form.addRow("Tamaño de imagen:", self.scale)
        form.addRow("", self.behind)
        form.addRow("Páginas:", self.pages)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addLayout(form)
        ll.addStretch(1)

        self.preview = QLabel("Vista previa")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(320, 420)
        self.preview.setStyleSheet("background:#5a5f66")
        self.error = QLabel()
        self.error.setStyleSheet("color:#b00")
        self.error.setWordWrap(True)
        right = QVBoxLayout()
        right.addWidget(self.preview, 1)
        right.addWidget(QLabel(f"<small>Vista previa de la página {page + 1}</small>"), 0, Qt.AlignCenter)

        top = QHBoxLayout()
        top.addWidget(left, 1)
        top.addLayout(right, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(top, 1)
        lay.addWidget(self.error)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("Aplicar marca de agua…")
        box.button(QDialogButtonBox.Cancel).setText("Cancelar")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self._render)
        for sig in (self.text.textChanged, self.image.textChanged, self.size.valueChanged, self.opacity.valueChanged,
                    self.rotation.valueChanged, self.position.currentIndexChanged, self.scale.valueChanged,
                    self.behind.toggled, self.r_text.toggled):
            sig.connect(lambda *_: self._changed())
        self._changed()

    def _pick(self):
        p, _ = QFileDialog.getOpenFileName(self, "Imagen de la marca de agua", "", IMG_FILTER)
        if p:
            self.image.setText(p)
            self.r_image.setChecked(True)

    def _pick_color(self):
        c = QColorDialog.getColor(self.color, self, "Color de la marca de agua")
        if c.isValid():
            self.color = c
            self._paint_color()
            self._changed()

    def _paint_color(self):
        self.btn_color.setText(self.color.name())
        self.btn_color.setStyleSheet(f"background:{self.color.name()}; color:white")

    def _changed(self):
        is_text = self.r_text.isChecked()
        for w in (self.text, self.btn_color, self.size, self.rotation):
            w.setEnabled(is_text)
        self.scale.setEnabled(not is_text)
        self.opacity_label.setText(f"{self.opacity.value()} %")
        self._timer.start()

    def options(self) -> dict:
        is_text = self.r_text.isChecked()
        return dict(text=self.text.toPlainText() if is_text else None,
                    image=self.image.text() if not is_text else None,
                    opacity=self.opacity.value() / 100, rotation=self.rotation.value(),
                    fontsize=self.size.value() or None, color=self.color.name(),
                    position=self.position.currentData(), behind=self.behind.isChecked(),
                    scale=self.scale.value() / 100)

    def _render(self):
        try:
            with pymupdf.open(stream=self.source.read_bytes(), filetype="pdf") as d:
                if d.needs_pass:
                    d.authenticate(self.password or "")
                one = pymupdf.open()
                one.insert_pdf(d, from_page=self.page, to_page=self.page)
            core.apply_watermark(one, **self.options())
            page = one[0]
            z = min(self.preview.width() / page.rect.width, self.preview.height() / page.rect.height) * 0.95
            pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
            one.close()
            self.preview.setPixmap(_pix_to_qpixmap(pix))
            self.error.setText("")
        except Exception as exc:
            self.error.setText(str(exc))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._timer.start()

    def accept(self):
        o = self.options()
        if o["text"] is not None and not o["text"].strip():
            return QMessageBox.warning(self, "Marca de agua", "Escriba el texto de la marca de agua.")
        if o["image"] is not None and not Path(o["image"]).exists():
            return QMessageBox.warning(self, "Marca de agua", "Elija la imagen de la marca de agua.")
        super().accept()


class FormDialog(QDialog):
    """Muestra los campos del formulario para diligenciarlos."""

    def __init__(self, fields: list[core.FormField], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diligenciar formulario")
        self.resize(620, 620)
        self.editors: dict[str, tuple[core.FormField, QWidget]] = {}
        inner = QWidget()
        col = QVBoxLayout(inner)
        by_page: dict[int, list[core.FormField]] = {}
        for f in fields:
            by_page.setdefault(f.page, []).append(f)
        for pno in sorted(by_page):
            box = QGroupBox(f"Página {pno + 1}")
            form = QFormLayout(box)
            for f in by_page[pno]:
                w = self._editor(f)
                w.setEnabled(not f.readonly)
                label = f.label or f.name
                if f.readonly:
                    label += " (solo lectura)"
                lab = QLabel(label)
                lab.setToolTip(f"Nombre del campo: {f.name}")
                lab.setWordWrap(True)
                form.addRow(lab, w)
                self.editors[f.name] = (f, w)
            col.addWidget(box)
        col.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        self.flatten = QCheckBox("Aplanar: convertir los datos en texto fijo (ya no se podrán editar)")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"{len(fields)} campo(s). Escriba o elija los valores y guarde en un archivo nuevo."))
        lay.addWidget(scroll, 1)
        lay.addWidget(self.flatten)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Guardar formulario…")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    @staticmethod
    def _editor(f: core.FormField) -> QWidget:
        if f.kind == "casilla":
            w = QCheckBox("Marcar")
            w.setChecked(bool(f.value))
        elif f.kind in ("lista", "opción"):
            w = QComboBox()
            w.addItem("(sin elegir)", "")
            for o in f.options:
                w.addItem(o, o)
            i = w.findData(str(f.value))
            w.setCurrentIndex(max(i, 0))
        elif f.multiline:
            w = QPlainTextEdit(str(f.value))
            w.setMaximumHeight(80)
        else:
            w = QLineEdit(str(f.value))
            if f.max_length:
                w.setMaxLength(f.max_length)
        return w

    def values(self) -> dict[str, object]:
        out = {}
        for name, (f, w) in self.editors.items():
            if f.readonly:
                continue
            if isinstance(w, QCheckBox):
                v = w.isChecked()
            elif isinstance(w, QComboBox):
                v = w.currentData()
            elif isinstance(w, QPlainTextEdit):
                v = w.toPlainText()
            else:
                v = w.text()
            if v != f.value:
                out[name] = v
        return out


def _row(*widgets) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        lay.addWidget(x)
    return w

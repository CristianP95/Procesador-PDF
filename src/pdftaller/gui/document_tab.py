"""Pestaña de documento: miniaturas reordenables + vista previa grande.

Todos los cambios (orden, rotación, eliminación, zonas de censura y firmas) quedan
pendientes hasta Guardar; entonces se aplican con las funciones de ``pdftaller.core``.
"""
from __future__ import annotations

import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPalette, QPixmap, QTransform
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidgetItem, QScrollArea, QSplitter, QToolButton, QVBoxLayout, QWidget,
)

from pdftaller import core

from .page_widgets import PageList, PageView

THUMB = 120
ROLE_PAGE = Qt.UserRole        # índice original (base 0)
ROLE_ROT = Qt.UserRole + 1     # rotación pendiente en grados


@dataclass
class Mark:
    kind: str                  # "redact" | "image"
    page: int                  # índice original
    rect: tuple                # puntos PDF, sistema sin rotar
    image: str | None = None


def _to_qpixmap(pix: pymupdf.Pixmap) -> QPixmap:
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(img)


class DocumentTab(QWidget):
    modified_changed = Signal(bool)
    status = Signal(str)

    def __init__(self, path: str | Path, password: str | None = None, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self.password = password
        self.zoom = 1.0
        self._fitted = False
        self.marks: list[Mark] = []
        self.signature_image: str | None = None
        self._modified = False
        self._doc: pymupdf.Document | None = None
        self._thumbs: list[QPixmap] = []
        self._preview_page: int | None = None

        self.info = QLabel()
        self.info.setWordWrap(True)
        self.pages = PageList(THUMB)
        self.pages.order_changed.connect(self._on_order_changed)
        self.pages.currentItemChanged.connect(lambda *_: self.show_preview())

        # --- vista previa
        self.view = PageView()
        self.view.rect_drawn.connect(self._on_rect_drawn)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.view)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setBackgroundRole(QPalette.Dark)
        bar = QHBoxLayout()
        self.page_label = QLabel()
        bar.addWidget(self.page_label)
        bar.addStretch()
        self.btn_redact = self._tool(bar, "■ Censurar zona", "Dibuje recuadros sobre la página para censurarlos", True)
        self.btn_sign = self._tool(bar, "✍ Firmar", "Dibuje el recuadro donde irá la firma (imagen)", True)
        self._tool(bar, "↶ Deshacer marca", "Quita la última zona o firma de esta página").clicked.connect(self.undo_mark)
        bar.addSpacing(12)
        self._tool(bar, "−", "Alejar").clicked.connect(lambda: self.set_zoom(self.zoom / 1.25))
        self._tool(bar, "+", "Acercar").clicked.connect(lambda: self.set_zoom(self.zoom * 1.25))
        self._tool(bar, "Ajustar", "Ajustar al ancho").clicked.connect(self.fit_width)
        self.btn_redact.toggled.connect(lambda on: self._set_mode("redact" if on else None))
        self.btn_sign.toggled.connect(lambda on: self._set_mode("image" if on else None))
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addLayout(bar)
        rl.addWidget(self.scroll, 1)

        split = QSplitter()
        split.addWidget(self.pages)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([480, 720])
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addWidget(split, 1)
        self.reload()

    def _tool(self, bar, text, tip, checkable=False) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        bar.addWidget(b)
        return b

    # ------------------------------------------------------------ estado
    @property
    def modified(self) -> bool:
        return self._modified

    @property
    def has_redactions(self) -> bool:
        return any(m.kind == "redact" for m in self.marks)

    def _set_modified(self, value: bool):
        if value != self._modified:
            self._modified = value
            self.modified_changed.emit(value)
        self._update_info()

    def title(self) -> str:
        return ("● " if self._modified else "") + self.path.name

    def _update_info(self):
        n = self.pages.count()
        parts = [str(self.path), f"{n} páginas"]
        if self.password:
            parts.append("protegido")
        nr = sum(m.kind == "redact" for m in self.marks)
        ni = sum(m.kind == "image" for m in self.marks)
        if nr:
            parts.append(f"{nr} zona(s) por censurar")
        if ni:
            parts.append(f"{ni} firma(s)")
        if self._modified:
            parts.append("cambios sin guardar (Ctrl+S)")
        self.info.setText("  ·  ".join(parts) +
                          "\nArrastre las miniaturas para reordenar · clic derecho para más opciones.")

    # ------------------------------------------------------------ carga
    def reload(self):
        if self._doc is not None:
            self._doc.close()
        self.pages.blockSignals(True)
        self.pages.clear()
        self._thumbs.clear()
        self.marks.clear()
        self._doc = pymupdf.open(stream=self.path.read_bytes(), filetype="pdf")
        if self._doc.needs_pass:
            self._doc.authenticate(self.password or "")
        for page in self._doc:
            zoom = THUMB / max(page.rect.width, page.rect.height)
            self._thumbs.append(_to_qpixmap(page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)))
            item = QListWidgetItem(QIcon(self._thumbs[-1]), str(page.number + 1))
            item.setData(ROLE_PAGE, page.number)
            item.setData(ROLE_ROT, 0)
            item.setTextAlignment(Qt.AlignHCenter)
            self.pages.addItem(item)
        self.pages.blockSignals(False)
        if self.pages.count():
            self.pages.setCurrentRow(0)
        self._set_modified(False)
        self._update_info()
        self.show_preview()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._fitted:
            self._fitted = True
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.fit_width)

    def closeEvent(self, e):
        if self._doc is not None:
            self._doc.close()
        super().closeEvent(e)

    def _on_order_changed(self):
        self._renumber()
        self._set_modified(True)

    def _renumber(self):
        for i in range(self.pages.count()):
            it = self.pages.item(i)
            orig = it.data(ROLE_PAGE) + 1
            it.setText(str(i + 1) if orig == i + 1 else f"{i + 1}  (era {orig})")
            it.setToolTip(f"Posición {i + 1} · página original {orig}")

    # ------------------------------------------------------------ vista previa
    def _render_matrix(self, orig: int, pending: int) -> tuple[pymupdf.Matrix, pymupdf.Matrix]:
        """Matriz de render y matriz 'sin rotar → píxel' para la página mostrada."""
        page = self._doc[orig]
        m = pymupdf.Matrix(self.zoom, self.zoom).prerotate(pending)
        t = page.rotation_matrix * m
        bbox = pymupdf.Rect(0, 0, page.cropbox.width, page.cropbox.height) * t
        t = t * pymupdf.Matrix(1, 0, 0, 1, -bbox.x0, -bbox.y0)
        return m, t

    def show_preview(self):
        it = self.pages.currentItem()
        if it is None or self._doc is None:
            self.view.set_page(QPixmap(), [])
            self.page_label.setText("")
            self._preview_page = None
            return
        orig, pending = it.data(ROLE_PAGE), it.data(ROLE_ROT)
        self._preview_page = orig
        m, t = self._render_matrix(orig, pending)
        pix = _to_qpixmap(self._doc[orig].get_pixmap(matrix=m, alpha=False))
        marks = []
        for mk in self.marks:
            if mk.page == orig:
                r = pymupdf.Rect(mk.rect) * t
                img = QPixmap(mk.image).transformed(QTransform().rotate(pending)) if mk.image else None
                marks.append((mk.kind, QRectF(r.x0, r.y0, r.width, r.height), img))
        self.view.set_page(pix, marks)
        self.page_label.setText(f"Página {self.pages.row(it) + 1} de {self.pages.count()}  ·  {int(self.zoom * 100)} %")

    def set_zoom(self, z: float):
        self.zoom = max(0.2, min(z, 5.0))
        self.show_preview()

    def fit_width(self):
        it = self.pages.currentItem()
        if it is None:
            return
        page = self._doc[it.data(ROLE_PAGE)]
        rot = (page.rotation + it.data(ROLE_ROT)) % 180
        width = page.cropbox.height if rot else page.cropbox.width
        self.set_zoom((self.scroll.viewport().width() - 20) / width)

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.zoom * (1.1 if e.angleDelta().y() > 0 else 1 / 1.1))
            e.accept()
        else:
            super().wheelEvent(e)

    # ------------------------------------------------------------ zonas y firmas
    def _set_mode(self, mode: str | None):
        if mode == "image" and not self.signature_image:
            self.status.emit("Elija primero la imagen de la firma")
            self.request_signature_image()
            if not self.signature_image:
                self.btn_sign.setChecked(False)
                return
        for b, m in ((self.btn_redact, "redact"), (self.btn_sign, "image")):
            if m != mode and b.isChecked():
                b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(False)
        self.view.set_mode(mode)

    def request_signature_image(self):
        from PySide6.QtWidgets import QFileDialog
        p, _ = QFileDialog.getOpenFileName(self, "Imagen de la firma", "",
                                           "Imágenes (*.png *.jpg *.jpeg *.bmp)")
        if p:
            self.signature_image = p

    def _on_rect_drawn(self, r: QRectF):
        if self._preview_page is None or not self.view.mode:
            return
        it = self.pages.currentItem()
        _, t = self._render_matrix(self._preview_page, it.data(ROLE_ROT))
        pr = pymupdf.Rect(r.x(), r.y(), r.x() + r.width(), r.y() + r.height()) * ~t
        kind = self.view.mode
        self.marks.append(Mark(kind, self._preview_page, tuple(pr),
                               self.signature_image if kind == "image" else None))
        self._set_modified(True)
        self.show_preview()

    def undo_mark(self):
        for i in range(len(self.marks) - 1, -1, -1):
            if self.marks[i].page == self._preview_page:
                del self.marks[i]
                self._set_modified(bool(self.marks) or self._order_or_rotation_changed())
                self.show_preview()
                return

    def _order_or_rotation_changed(self) -> bool:
        return any(self.pages.item(i).data(ROLE_PAGE) != i or self.pages.item(i).data(ROLE_ROT)
                   for i in range(self.pages.count())) or self.pages.count() != len(self._thumbs)

    # ------------------------------------------------------------ ediciones de páginas
    def selected_items(self) -> list[QListWidgetItem]:
        return sorted(self.pages.selectedItems(), key=self.pages.row)

    def rotate_selected(self, degrees: int) -> bool:
        items = self.selected_items()
        for it in items:
            rot = (it.data(ROLE_ROT) + degrees) % 360
            it.setData(ROLE_ROT, rot)
            it.setIcon(QIcon(self._thumbs[it.data(ROLE_PAGE)].transformed(QTransform().rotate(rot))))
        if items:
            self._set_modified(True)
            self.show_preview()
        return bool(items)

    def delete_selected(self) -> int:
        items = self.selected_items()
        if len(items) >= self.pages.count():
            return -1
        for it in items:
            self.pages.takeItem(self.pages.row(it))
        if items:
            self._renumber()
            self._set_modified(True)
        return len(items)

    def move_selected(self, where: str | int):
        rows = self.pages.selected_rows()
        if not rows:
            return
        targets = {"inicio": 0, "final": self.pages.count(),
                   "izquierda": max(0, rows[0] - 1), "derecha": min(self.pages.count(), rows[-1] + 2)}
        self.pages.move_rows(rows, targets[where] if isinstance(where, str) else where)

    def selected_page_spec(self) -> str:
        return ",".join(str(self.pages.row(it) + 1) for it in self.selected_items())

    # ------------------------------------------------------------ guardar
    def write_to(self, output: str | Path) -> Path:
        """Escribe el documento con todos los cambios pendientes en ``output``."""
        order = [self.pages.item(i).data(ROLE_PAGE) for i in range(self.pages.count())]
        out = core.reorder(self.path, output, order, password=self.password)
        by_deg: dict[int, list[int]] = defaultdict(list)
        for pos in range(self.pages.count()):
            rot = self.pages.item(pos).data(ROLE_ROT)
            if rot:
                by_deg[rot].append(pos)
        for deg, positions in by_deg.items():
            core.rotate_pages(out, out, positions, deg, password=self.password)
        # Las marcas usan el índice original: se traducen a la nueva posición (si la página sigue).
        pos_of = {orig: pos for pos, orig in enumerate(order)}
        areas: dict[int, list] = defaultdict(list)
        images = []
        for m in self.marks:
            if m.page not in pos_of:
                continue
            if m.kind == "redact":
                areas[pos_of[m.page]].append(m.rect)
            else:
                images.append((pos_of[m.page], m.rect, m.image))
        if areas:
            core.redact(out, out, areas=areas, remove_metadata=False, password=self.password)
        if images:
            core.insert_images(out, out, images, password=self.password)
        return out

    def materialize(self) -> Path:
        """Ruta con el contenido actual: el original o una copia temporal con los cambios."""
        if not self._modified:
            return self.path
        tmp = Path(tempfile.mkdtemp(prefix="pdftaller_")) / self.path.name
        return self.write_to(tmp)

    def save(self, output: str | Path | None = None) -> Path:
        out = self.write_to(output or self.path)
        self.path = Path(out)
        self.reload()
        return self.path

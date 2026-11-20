"""Pestaña de documento: miniaturas de páginas que se pueden reordenar, rotar y eliminar."""
from __future__ import annotations

import tempfile
from collections import defaultdict
from pathlib import Path

import pymupdf
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap, QTransform
from PySide6.QtWidgets import QAbstractItemView, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from pdftaller import core

THUMB = 180
ROLE_PAGE = Qt.UserRole        # índice original (base 0)
ROLE_ROT = Qt.UserRole + 1     # rotación pendiente en grados


class DocumentTab(QWidget):
    modified_changed = Signal(bool)

    def __init__(self, path: str | Path, password: str | None = None, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self.password = password
        self._modified = False
        self._pixmaps: list[QPixmap] = []

        self.info = QLabel()
        self.pages = QListWidget()
        self.pages.setViewMode(QListWidget.IconMode)
        self.pages.setIconSize(QSize(THUMB, THUMB))
        self.pages.setResizeMode(QListWidget.Adjust)
        self.pages.setSpacing(10)
        self.pages.setMovement(QListWidget.Snap)
        self.pages.setDragDropMode(QAbstractItemView.InternalMove)
        self.pages.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.pages.setUniformItemSizes(True)
        self.pages.model().rowsMoved.connect(lambda *_: self._set_modified(True))

        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addWidget(self.pages)
        self.reload()

    # ------------------------------------------------------------ estado
    @property
    def modified(self) -> bool:
        return self._modified

    def _set_modified(self, value: bool):
        if value != self._modified:
            self._modified = value
            self.modified_changed.emit(value)
        self._update_info()

    def title(self) -> str:
        return ("● " if self._modified else "") + self.path.name

    def _update_info(self):
        n = self.pages.count()
        enc = " · protegido" if self.password else ""
        hint = " · cambios sin guardar" if self._modified else ""
        self.info.setText(f"{self.path}  ·  {n} páginas{enc}{hint}   —   Arrastre las miniaturas para reordenar.")

    # ------------------------------------------------------------ carga
    def reload(self):
        self.pages.clear()
        self._pixmaps.clear()
        with pymupdf.open(stream=self.path.read_bytes(), filetype="pdf") as doc:
            if doc.needs_pass:
                doc.authenticate(self.password or "")
            for page in doc:
                zoom = THUMB / max(page.rect.width, page.rect.height)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
                self._pixmaps.append(QPixmap.fromImage(img))
                item = QListWidgetItem(QIcon(self._pixmaps[-1]), str(page.number + 1))
                item.setData(ROLE_PAGE, page.number)
                item.setData(ROLE_ROT, 0)
                item.setTextAlignment(Qt.AlignHCenter)
                self.pages.addItem(item)
        self._set_modified(False)
        self._update_info()

    # ------------------------------------------------------------ ediciones pendientes
    def selected_items(self) -> list[QListWidgetItem]:
        return sorted(self.pages.selectedItems(), key=self.pages.row)

    def rotate_selected(self, degrees: int) -> bool:
        items = self.selected_items()
        for it in items:
            rot = (it.data(ROLE_ROT) + degrees) % 360
            it.setData(ROLE_ROT, rot)
            pm = self._pixmaps[it.data(ROLE_PAGE)].transformed(QTransform().rotate(rot))
            it.setIcon(QIcon(pm))
        if items:
            self._set_modified(True)
        return bool(items)

    def delete_selected(self) -> int:
        items = self.selected_items()
        if len(items) >= self.pages.count():
            return -1
        for it in items:
            self.pages.takeItem(self.pages.row(it))
        if items:
            self._set_modified(True)
        return len(items)

    def selected_page_spec(self) -> str:
        """Páginas seleccionadas en notación base 1 según la posición actual."""
        return ",".join(str(self.pages.row(it) + 1) for it in self.selected_items())

    # ------------------------------------------------------------ guardar
    def write_to(self, output: str | Path) -> Path:
        """Escribe el documento con los cambios pendientes en ``output``."""
        order = [self.pages.item(i).data(ROLE_PAGE) for i in range(self.pages.count())]
        out = core.reorder(self.path, output, order, password=self.password)
        by_deg: dict[int, list[int]] = defaultdict(list)
        for pos in range(self.pages.count()):
            rot = self.pages.item(pos).data(ROLE_ROT)
            if rot:
                by_deg[rot].append(pos)
        for deg, positions in by_deg.items():
            core.rotate_pages(out, out, positions, deg, password=self.password)
        return out

    def materialize(self) -> Path:
        """Ruta con el contenido actual: el archivo original o una copia temporal con los cambios."""
        if not self._modified:
            return self.path
        tmp = Path(tempfile.mkdtemp(prefix="pdftaller_")) / self.path.name
        return self.write_to(tmp)

    def save(self, output: str | Path | None = None) -> Path:
        out = self.write_to(output or self.path)
        self.path = Path(out)
        self.reload()
        return self.path

"""Widgets de páginas: lista de miniaturas reordenable y vista previa con dibujo de zonas."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListView, QListWidget, QWidget


class PageList(QListWidget):
    """Miniaturas en cuadrícula. El arrastre inserta las páginas en el punto exacto donde se sueltan."""

    order_changed = Signal()

    def __init__(self, thumb: int, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setIconSize(QSize(thumb, thumb))
        self.setGridSize(QSize(thumb + 24, thumb + 34))
        self.setSpacing(6)
        self.setUniformItemSizes(True)
        self.setMovement(QListView.Snap)  # el soltado lo gestiona dropEvent (inserción real en el orden)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setStyleSheet("QListWidget { background: #e4e6ea; }")

    # -- movimiento
    def selected_rows(self) -> list[int]:
        return sorted(self.row(it) for it in self.selectedItems())

    def drop_row_at(self, pos: QPoint) -> int:
        """Fila de inserción para un punto: antes o después del ítem según la mitad donde caiga."""
        idx = self.indexAt(pos)
        if not idx.isValid():
            # Espacio vacío: buscar el ítem más cercano en la misma fila visual
            best, best_d = self.count(), None
            for r in range(self.count()):
                rect = self.visualRect(self.model().index(r, 0))
                if rect.top() <= pos.y() <= rect.bottom():
                    d = abs(rect.center().x() - pos.x())
                    if best_d is None or d < best_d:
                        best_d, best = d, (r if pos.x() < rect.center().x() else r + 1)
            return best
        rect = self.visualRect(idx)
        return idx.row() + (1 if pos.x() > rect.center().x() else 0)

    def move_rows(self, rows: list[int], target: int, *, final: bool = False):
        """Mueve las filas ``rows`` al punto de inserción ``target`` (0..count, posiciones actuales).

        Con ``final=True``, ``target`` es la posición donde debe quedar la primera página movida.
        """
        rows = sorted(set(rows))
        if not rows:
            return
        if final:
            target = max(0, min(target, self.count() - len(rows)))
        else:
            target = max(0, min(target, self.count()))
            target -= sum(1 for r in rows if r < target)
        items = [self.takeItem(r) for r in reversed(rows)][::-1]
        for i, it in enumerate(items):
            self.insertItem(target + i, it)
        self.clearSelection()
        for it in items:
            it.setSelected(True)
        self.setCurrentItem(items[0])
        self.doItemsLayout()
        self.order_changed.emit()

    def dropEvent(self, e):
        if e.source() is not self:
            e.ignore()
            return
        self.move_rows(self.selected_rows(), self.drop_row_at(e.position().toPoint()))
        # IgnoreAction evita que Qt borre las páginas "movidas" al terminar el arrastre.
        e.setDropAction(Qt.IgnoreAction)
        e.accept()


class PageView(QWidget):
    """Muestra una página grande. En modo dibujo permite trazar recuadros con el ratón."""

    rect_drawn = Signal(QRectF)       # en píxeles de la imagen mostrada

    COLORS = {"redact": QColor(0, 0, 0, 170), "image": QColor(30, 110, 230, 90)}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix = QPixmap()
        self._marks: list[tuple[str, QRectF, QPixmap | None]] = []
        self._start: QPoint | None = None
        self._current: QRect | None = None
        self.mode: str | None = None
        self.setMouseTracking(True)

    def set_page(self, pix: QPixmap, marks):
        self._pix = pix
        self._marks = marks
        self.setFixedSize(pix.size() if not pix.isNull() else QSize(10, 10))
        self.update()

    def set_mode(self, mode: str | None):
        self.mode = mode
        self.setCursor(Qt.CrossCursor if mode else Qt.ArrowCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        if not self._pix.isNull():
            p.drawPixmap(0, 0, self._pix)
        for kind, r, img in self._marks:
            if kind == "image" and img is not None and not img.isNull():
                scaled = img.scaled(r.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                p.drawPixmap(r.topLeft().toPoint(), scaled)
                p.setPen(QPen(QColor(30, 110, 230), 1, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(self.COLORS.get(kind, QColor(0, 0, 0, 120)))
            p.drawRect(r)
        if self._current is not None:
            p.setPen(QPen(QColor(220, 40, 40), 2, Qt.DashLine))
            p.setBrush(QColor(220, 40, 40, 40))
            p.drawRect(self._current)

    def mousePressEvent(self, e):
        if self.mode and e.button() == Qt.LeftButton:
            self._start = e.position().toPoint()
            self._current = QRect(self._start, self._start)

    def mouseMoveEvent(self, e):
        if self._start is not None:
            self._current = QRect(self._start, e.position().toPoint()).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, e):
        if self._start is None:
            return
        r = self._current
        self._start, self._current = None, None
        self.update()
        if r is not None and r.width() > 4 and r.height() > 4:
            self.rect_drawn.emit(QRectF(r))

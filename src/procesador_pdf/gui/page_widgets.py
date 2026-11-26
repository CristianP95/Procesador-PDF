"""Widgets de páginas: lista de miniaturas reordenable y vista previa con dibujo de zonas."""
from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QApplication, QListView, QListWidget, QMenu, QWidget


class PageList(QListWidget):
    """Miniaturas en cuadrícula con arrastre propio.

    El arrastre interno de Qt en modo icono no reordena de forma fiable (sobre todo hacia
    atrás), así que se implementa a mano: se pulsa sobre una página seleccionada, se arrastra
    y se suelta; una línea azul indica dónde se insertará.
    """

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
        self.setMovement(QListView.Static)
        self.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setStyleSheet("QListWidget { background: #e4e6ea; }")
        self._press: QPoint | None = None
        self._dragging = False
        self._drop_row: int | None = None
        self._drop: tuple[int, int, bool] | None = None
        self._last_pos: QPoint | None = None
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(40)
        self._scroll_timer.timeout.connect(self._tick_autoscroll)
        self.locked = False

    # -- movimiento
    def selected_rows(self) -> list[int]:
        return sorted(self.row(it) for it in self.selectedItems())

    def _rect(self, r: int) -> QRect:
        return self.visualRect(self.model().index(r, 0))

    def _same_line(self, a: int, b: int) -> bool:
        return 0 <= a < self.count() and 0 <= b < self.count() and \
            abs(self._rect(a).top() - self._rect(b).top()) < self._rect(a).height() / 2

    def _horizontal(self, r: int) -> bool:
        """``True`` si el ítem ``r`` tiene vecinos en su misma fila (cuadrícula);
        ``False`` si las páginas están en una sola columna (se decide por arriba/abajo)."""
        if self.count() < 2:
            return True
        return self._same_line(r, r - 1) or self._same_line(r, r + 1)

    def drop_target(self, pos: QPoint) -> tuple[int, int, bool]:
        """``(fila_de_inserción, ítem_de_referencia, después)`` para un punto del viewport.

        Se toma la página más cercana al cursor (también si está en el hueco entre filas) y se
        inserta antes o después según el lado: izquierda/derecha en cuadrícula, arriba/abajo
        si hay una sola columna.
        """
        if not self.count():
            return 0, -1, False
        best, best_d = 0, None
        for r in range(self.count()):
            rect = self._rect(r)
            dx = max(rect.left() - pos.x(), 0, pos.x() - rect.right())
            dy = max(rect.top() - pos.y(), 0, pos.y() - rect.bottom())
            d = dx * dx + dy * dy * 4          # pesa más la distancia vertical (fila correcta)
            if best_d is None or d < best_d:
                best_d, best = d, r
        rect = self._rect(best)
        after = pos.x() > rect.center().x() if self._horizontal(best) else pos.y() > rect.center().y()
        return (best + 1 if after else best), best, after

    def drop_row_at(self, pos: QPoint) -> int:
        """Fila de inserción para un punto del viewport."""
        return self.drop_target(pos)[0]

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
        if [target + i for i in range(len(rows))] == rows:
            return  # no cambia nada
        self.about_to_change()
        items = [self.takeItem(r) for r in reversed(rows)][::-1]
        for i, it in enumerate(items):
            self.insertItem(target + i, it)
        self.clearSelection()
        for it in items:
            it.setSelected(True)
        self.setCurrentItem(items[0])
        self.doItemsLayout()
        self.order_changed.emit()

    def about_to_change(self):
        """Gancho para guardar el estado antes de un cambio (deshacer). Lo reemplaza la pestaña."""

    # -- arrastre propio
    def mousePressEvent(self, e):
        it = self.itemAt(e.position().toPoint())
        if e.button() == Qt.LeftButton and it is not None and it.isSelected() and not e.modifiers():
            # Pulsar sobre una selección existente: posible arrastre (no cambiar la selección aún)
            self._press = e.position().toPoint()
            self.setCurrentItem(it, QItemSelectionModel.NoUpdate)
            return
        self._press = e.position().toPoint() if (e.button() == Qt.LeftButton and it is not None) else None
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._press is not None and (e.buttons() & Qt.LeftButton):
            if not self._dragging and not self.locked and \
                    (pos - self._press).manhattanLength() >= QApplication.startDragDistance():
                if self.itemAt(self._press) is not None and self.itemAt(self._press).isSelected():
                    self._dragging = True
                    self.viewport().setCursor(Qt.ClosedHandCursor)
            if self._dragging:
                self._last_pos = pos
                if not self._scroll_timer.isActive():
                    self._scroll_timer.start()
                self._update_drop(pos)
                return
        super().mouseMoveEvent(e)

    def _update_drop(self, pos: QPoint):
        self._drop = self.drop_target(pos)
        self._drop_row = self._drop[0]
        self.viewport().update()

    def _tick_autoscroll(self):
        """Mientras se arrastra cerca del borde (o fuera), desplaza la lista aunque el ratón no se mueva."""
        if not self._dragging or self._last_pos is None:
            self._scroll_timer.stop()
            return
        bar, h, y = self.verticalScrollBar(), self.viewport().height(), self._last_pos.y()
        margin = 40
        if y < margin:
            bar.setValue(bar.value() - max(10, margin - y))
        elif y > h - margin:
            bar.setValue(bar.value() + max(10, y - h + margin))
        else:
            return
        self._update_drop(self._last_pos)

    def mouseReleaseEvent(self, e):
        if self._dragging:
            row = self.drop_row_at(e.position().toPoint())
            self._end_drag()
            self.move_rows(self.selected_rows(), row)
            return
        if self._press is not None and e.button() == Qt.LeftButton:
            it = self.itemAt(self._press)
            if it is not None and it.isSelected() and not e.modifiers():
                # Clic simple sobre una página ya seleccionada: dejar solo esa
                self.clearSelection()
                it.setSelected(True)
                self.setCurrentItem(it)
        self._end_drag()
        super().mouseReleaseEvent(e)

    def _end_drag(self):
        self._press, self._dragging, self._drop_row, self._drop, self._last_pos = None, False, None, None, None
        self._scroll_timer.stop()
        self.viewport().unsetCursor()
        self.viewport().update()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._dragging and self._drop is not None and self._drop[1] >= 0:
            _, ref, after = self._drop
            rect = self._rect(ref)
            p = QPainter(self.viewport())
            p.setPen(QPen(QColor(25, 118, 210), 4))
            if self._horizontal(ref):
                x = rect.right() + 4 if after else rect.left() - 4
                p.drawLine(x, rect.top(), x, rect.bottom())
            else:
                y = rect.bottom() + 4 if after else rect.top() - 4
                p.drawLine(rect.left(), y, rect.right(), y)


class PageView(QWidget):
    """Muestra una página grande. En modo dibujo permite trazar recuadros con el ratón."""

    rect_drawn = Signal(QRectF)       # en píxeles de la imagen mostrada
    mark_menu_requested = Signal(int, QPoint)   # índice de la marca bajo el cursor (-1 si ninguna), posición global

    COLORS = {"redact": QColor(0, 0, 0, 170), "redact-texto": QColor(120, 0, 0, 170),
              "image": QColor(30, 110, 230, 90)}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix = QPixmap()
        self._marks: list[tuple[str, QRectF, QPixmap | None, bool]] = []
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
        for kind, r, img, selected in self._marks:
            if kind == "image" and img is not None and not img.isNull():
                scaled = img.scaled(r.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                p.drawPixmap(r.topLeft().toPoint(), scaled)
                p.setPen(QPen(QColor(30, 110, 230), 1, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
            elif kind == "outline":      # vista de resultado: la página ya viene censurada
                p.setPen(QPen(QColor(220, 40, 40), 1, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(self.COLORS.get(kind, QColor(0, 0, 0, 120)))
            p.drawRect(r)
            if selected:
                p.setPen(QPen(QColor(255, 190, 0), 3))
                p.setBrush(Qt.NoBrush)
                p.drawRect(r.adjusted(-3, -3, 3, 3))
        if self._current is not None:
            p.setPen(QPen(QColor(220, 40, 40), 2, Qt.DashLine))
            p.setBrush(QColor(220, 40, 40, 40))
            p.drawRect(self._current)

    def contextMenuEvent(self, e):
        idx = -1
        for i, (_, r, _, _) in enumerate(self._marks):
            if r.contains(e.pos().toPointF()):
                idx = i
        self.mark_menu_requested.emit(idx, e.globalPos())

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

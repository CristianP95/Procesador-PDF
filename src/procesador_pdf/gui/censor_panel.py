"""Panel de censura: une la búsqueda por texto y el dibujo de zonas en una sola herramienta.

Todas las zonas (encontradas por texto o dibujadas) aparecen en la misma lista y en la vista
previa; se pueden revisar, quitar y ver cómo quedará la página antes de aplicar.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from .document_tab import DocumentTab


class CensorPanel(QWidget):
    def __init__(self, tab: "DocumentTab"):
        super().__init__(tab)
        self.tab = tab
        self.setMinimumWidth(270)
        self.setMaximumWidth(380)

        title = QLabel("<b>■ Censurar</b>")
        help_ = QLabel("Busque textos o dibuje zonas. Todo queda en la lista de abajo y en la vista "
                       "previa para revisarlo. Nada se borra hasta aplicar.")
        help_.setWordWrap(True)

        # --- por texto
        self.terms = QPlainTextEdit()
        self.terms.setPlaceholderText("Un texto por línea, p. ej.:\nJuan Pérez\n1234567890")
        self.terms.setMaximumHeight(90)
        self.regex = QCheckBox("Expresiones regulares (\\d{10} = 10 dígitos)")
        self.btn_search = QPushButton("Buscar y marcar")
        self.btn_search.clicked.connect(self._search)
        self.search_result = QLabel()
        self.search_result.setWordWrap(True)
        g1 = QGroupBox("1. Por texto")
        l1 = QVBoxLayout(g1)
        l1.addWidget(self.terms)
        l1.addWidget(self.regex)
        l1.addWidget(self.btn_search)
        l1.addWidget(self.search_result)

        # --- por zona
        self.btn_draw = QPushButton("Dibujar zonas sobre la página")
        self.btn_draw.setCheckable(True)
        self.btn_draw.toggled.connect(self._toggle_draw)
        g2 = QGroupBox("2. Por zona")
        l2 = QVBoxLayout(g2)
        l2.addWidget(self.btn_draw)
        hint = QLabel("<small>Con el botón activo, arrastre el ratón sobre la vista previa.</small>")
        hint.setWordWrap(True)
        l2.addWidget(hint)

        # --- lista
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self._selection_changed)
        self.list.itemDoubleClicked.connect(lambda it: self._go_to(it))
        self.list.installEventFilter(self)
        self.btn_remove = QPushButton("Quitar seleccionadas")
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear = QPushButton("Quitar todas")
        self.btn_clear.clicked.connect(self._remove_all)
        self.g3 = QGroupBox("3. Zonas marcadas")
        l3 = QVBoxLayout(self.g3)
        l3.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(self.btn_remove)
        row.addWidget(self.btn_clear)
        l3.addLayout(row)

        # --- aplicar
        self.result_view = QCheckBox("Ver cómo quedará (resultado final)")
        self.result_view.toggled.connect(self._toggle_result)
        self.meta = QCheckBox("Borrar también los metadatos (autor, título…)")
        self.meta.setChecked(True)
        self.btn_apply = QPushButton("Aplicar censura y guardar…")
        self.btn_apply.setStyleSheet("font-weight: bold")
        self.btn_close = QPushButton("Cerrar panel")
        self.btn_close.clicked.connect(self.tab.hide_censor_panel)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 0, 0, 0)
        lay.addWidget(title)
        lay.addWidget(help_)
        lay.addWidget(g1)
        lay.addWidget(g2)
        lay.addWidget(self.g3, 1)
        lay.addWidget(self.result_view)
        lay.addWidget(self.meta)
        lay.addWidget(self.btn_apply)
        lay.addWidget(self.btn_close)
        self._updating = False

    # ------------------------------------------------------------ acciones
    def _search(self):
        terms = [t.strip() for t in self.terms.toPlainText().splitlines() if t.strip()]
        if not terms:
            self.search_result.setText("<span style='color:#b00'>Escriba al menos un texto.</span>")
            return
        try:
            n_found, n_new, pages = self.tab.search_and_mark(terms, self.regex.isChecked())
        except Exception as exc:
            self.search_result.setText(f"<span style='color:#b00'>{exc}</span>")
            return
        if not n_found:
            self.search_result.setText("No se encontró ninguna coincidencia. Si el documento es escaneado, "
                                       "use primero Optimizar → Reconocer texto.")
            return
        extra = "" if n_new == n_found else f" ({n_found - n_new} ya estaban marcadas)"
        self.search_result.setText(f"{n_found} coincidencia(s) en página(s) {pages}. "
                                   f"Se marcaron {n_new}{extra}.")

    def _toggle_draw(self, on: bool):
        if self.tab.btn_redact.isChecked() != on:
            self.tab.btn_redact.setChecked(on)
        if on and not self.tab.btn_redact.isChecked():      # sin permiso para editar
            self.btn_draw.blockSignals(True)
            self.btn_draw.setChecked(False)
            self.btn_draw.blockSignals(False)

    def sync_draw(self, on: bool):
        self.btn_draw.blockSignals(True)
        self.btn_draw.setChecked(on)
        self.btn_draw.blockSignals(False)

    def _toggle_result(self, on: bool):
        self.tab.preview_result = on
        self.tab.show_preview()

    def _marks_of(self, items):
        return [it.data(Qt.UserRole) for it in items]

    def _selection_changed(self):
        if self._updating:
            return
        marks = self._marks_of(self.list.selectedItems())
        self.tab.select_marks(marks)
        if len(marks) == 1:
            self.tab.go_to_page(marks[0].page)

    def _go_to(self, it: QListWidgetItem):
        self.tab.go_to_page(it.data(Qt.UserRole).page)

    def _remove_selected(self):
        self.tab.remove_marks(self._marks_of(self.list.selectedItems()))

    def _remove_all(self):
        self.tab.remove_marks([m for m in self.tab.marks if m.kind == "redact"])

    # ------------------------------------------------------------ refresco
    def refresh(self):
        """Reconstruye la lista a partir de las marcas de la pestaña."""
        self._updating = True
        selected = {id(m) for m in self.tab.selected_marks}
        self.list.clear()
        marks = [m for m in self.tab.marks if m.kind == "redact"]
        pos = self.tab.position_of_pages()
        marks.sort(key=lambda m: (pos.get(m.page, 10**6), m.rect[1], m.rect[0]))
        for m in marks:
            p = pos.get(m.page)
            where = f"Pág. {p + 1}" if p is not None else "Página eliminada"
            what = f"texto «{m.label}»" if m.origin == "texto" and m.label else \
                ("texto" if m.origin == "texto" else "zona dibujada")
            it = QListWidgetItem(f"{where} · {what}")
            it.setData(Qt.UserRole, m)
            it.setToolTip("Doble clic: ir a la página · Supr: quitar")
            self.list.addItem(it)
            if id(m) in selected:
                it.setSelected(True)
        self.g3.setTitle(f"3. Zonas marcadas ({len(marks)})")
        self.btn_remove.setEnabled(bool(marks))
        self.btn_clear.setEnabled(bool(marks))
        self.btn_apply.setEnabled(bool(marks))
        self._updating = False

    def eventFilter(self, obj, e):
        # Supr en la lista quita zonas (y no elimina páginas, que es el atajo global)
        if obj is self.list and e.type() in (QEvent.ShortcutOverride, QEvent.KeyPress) and \
                e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            e.accept()
            if e.type() == QEvent.KeyPress:
                self._remove_selected()
            return True
        return super().eventFilter(obj, e)

"""Pestaña de documento: miniaturas reordenables + vista previa grande + panel de censura.

Todos los cambios (orden, rotación, eliminación, zonas de censura y firmas) quedan
pendientes hasta Guardar; entonces se aplican con las funciones de ``pdftaller.core``.

Deshacer (Ctrl+Z) recorre los cambios pendientes y, después, también los guardados:
antes de cada guardado se conserva una copia de la versión anterior durante la sesión.
"""
from __future__ import annotations

import copy
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPalette, QPixmap, QTransform
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidgetItem, QScrollArea, QSizePolicy, QSplitter, QToolButton, QVBoxLayout,
    QWidget,
)

from pdftaller import core

from .censor_panel import CensorPanel
from .page_widgets import PageList, PageView

THUMB = 120
ROLE_PAGE = Qt.UserRole        # índice original (base 0)
ROLE_ROT = Qt.UserRole + 1     # rotación pendiente en grados
MAX_UNDO = 100


@dataclass
class Mark:
    kind: str                  # "redact" | "image"
    page: int                  # índice original
    rect: tuple                # puntos PDF, sistema sin rotar
    image: str | None = None
    origin: str = "zona"       # "zona" (dibujada) | "texto" (búsqueda)
    label: str = ""            # texto encontrado (censura por texto)


def _to_qpixmap(pix: pymupdf.Pixmap) -> QPixmap:
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(img)


_SNAP_DIR: Path | None = None


def _snapshot(path: Path) -> Path:
    """Copia de seguridad de una versión del archivo (para deshacer tras guardar)."""
    global _SNAP_DIR
    if _SNAP_DIR is None:
        _SNAP_DIR = Path(tempfile.mkdtemp(prefix="pdftaller_versiones_"))
    dst = _SNAP_DIR / f"{len(list(_SNAP_DIR.iterdir())):05d}_{path.name}"
    shutil.copyfile(path, dst)
    return dst


PERM_NAMES = {"imprimir": "imprimir", "copiar": "copiar", "modificar": "modificar", "comentar": "comentar"}


class DocumentTab(QWidget):
    modified_changed = Signal(bool)
    status = Signal(str)
    history_changed = Signal()
    apply_censor_requested = Signal()

    def __init__(self, path: str | Path, password: str | None = None, parent=None):
        super().__init__(parent)
        self.path = Path(path)        # archivo en disco al que se guarda
        self._source = self.path      # de dónde se lee el contenido (difiere tras deshacer un guardado)
        self.password = password
        self.zoom = 1.0
        self._fitted = False
        self.marks: list[Mark] = []
        self.selected_marks: list[Mark] = []
        self.signature_image: str | None = None
        self.preview_result = False
        self._modified = False
        self._doc: pymupdf.Document | None = None
        self._thumbs: list[QPixmap] = []
        self._preview_page: int | None = None
        self._undo: list[tuple] = []          # (estado, descripción)
        self._redo: list[tuple] = []
        self._file_undo: list[tuple] = []     # versiones guardadas: (copia, estado, undo, redo, desc)
        self._file_redo: list[tuple] = []
        self.read_only = False     # documento con restricciones y sin contraseña de propietario
        self.restrictions: dict[str, bool] = {}
        self.signed = False        # tiene firmas digitales (editar las invalida)
        self.scrub_metadata = False

        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.pages = PageList(THUMB)
        self.pages.order_changed.connect(self._on_order_changed)
        self.pages.about_to_change = lambda: self.push_undo("mover páginas")
        self.pages.currentItemChanged.connect(lambda *_: self.show_preview())

        # --- vista previa
        self.view = PageView()
        self.view.rect_drawn.connect(self._on_rect_drawn)
        self.view.mark_menu_requested.connect(self._mark_menu)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.view)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setBackgroundRole(QPalette.Dark)
        bar = QHBoxLayout()
        self.page_label = QLabel()
        self.page_label.setMinimumWidth(10)
        self.page_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        bar.addWidget(self.page_label, 1)
        self.btn_redact = self._tool(bar, "■ Zona", "Censurar zona: dibuje recuadros sobre la página", True)
        self.btn_sign = self._tool(bar, "✍ Firma", "Dibuje el recuadro donde irá la imagen de su firma", True)
        bar.addSpacing(12)
        self._tool(bar, "−", "Alejar").clicked.connect(lambda: self.set_zoom(self.zoom / 1.25))
        self._tool(bar, "+", "Acercar").clicked.connect(lambda: self.set_zoom(self.zoom * 1.25))
        self._tool(bar, "Ajustar", "Ajustar al ancho").clicked.connect(self.fit_width)
        self.btn_redact.toggled.connect(lambda on: self._set_mode("redact" if on else None))
        self.btn_sign.toggled.connect(lambda on: self._set_mode("image" if on else None))
        center = QWidget()
        rl = QVBoxLayout(center)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addLayout(bar)
        rl.addWidget(self.scroll, 1)

        self.censor = CensorPanel(self)
        self.censor.hide()
        self.censor.btn_apply.clicked.connect(self.apply_censor_requested.emit)

        self.split = QSplitter()
        self.split.addWidget(self.pages)
        self.split.addWidget(center)
        self.split.addWidget(self.censor)
        self.split.setStretchFactor(0, 2)
        self.split.setStretchFactor(1, 3)
        self.split.setStretchFactor(2, 0)
        self.split.setChildrenCollapsible(False)
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addWidget(self.split, 1)
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
        self._renumber()
        if value != self._modified:
            self._modified = value
            self.modified_changed.emit(value)
        self._update_info()
        if self.censor.isVisible():
            self.censor.refresh()
        self.history_changed.emit()

    def title(self) -> str:
        return ("● " if self._modified else "") + self.path.name

    def _update_info(self):
        n = self.pages.count()
        parts = [str(self.path), f"{n} páginas"]
        if self.read_only:
            denied = [k for k, v in self.restrictions.items() if not v]
            parts.append("🔒 CON RESTRICCIONES (no permite: " + ", ".join(denied) + "). "
                         "Use Desbloquear con la contraseña de permisos")
        elif self.restrictions and not all(self.restrictions.values()):
            denied = [k for k, v in self.restrictions.items() if not v]
            parts.append("🔒 no permite: " + ", ".join(denied))
        elif self.password:
            parts.append("protegido")
        if self.signed:
            parts.append("✍ FIRMADO DIGITALMENTE: cualquier cambio invalidará la firma")
        nr = sum(m.kind == "redact" for m in self.marks)
        ni = sum(m.kind == "image" for m in self.marks)
        if nr:
            parts.append(f"{nr} zona(s) por censurar")
        if ni:
            parts.append(f"{ni} firma(s)")
        if self._modified:
            parts.append("cambios sin guardar (Ctrl+S)")
        self.info.setText("  ·  ".join(parts) +
                          "\nArrastre las miniaturas para reordenar · clic derecho para más opciones · "
                          "Ctrl+Z deshace.")

    # ------------------------------------------------------------ carga
    def reload(self, *, from_disk: bool = True):
        """Vuelve a leer el documento. ``from_disk``: desde ``path`` (descarta la versión de deshacer)."""
        if from_disk:
            self._source = self.path
        if self._doc is not None:
            self._doc.close()
        self.pages.blockSignals(True)
        self.pages.clear()
        self._thumbs.clear()
        self.marks.clear()
        self.selected_marks.clear()
        self._doc = pymupdf.open(stream=self._source.read_bytes(), filetype="pdf")
        auth = 0
        if self._doc.needs_pass:
            auth = self._doc.authenticate(self.password or "")
        elif self.password:
            auth = self._doc.authenticate(self.password)
        encrypted = bool(self._doc.metadata.get("encryption"))
        owner = bool(auth & 4)
        p = self._doc.permissions
        self.restrictions = {} if not encrypted or owner else {
            "imprimir": bool(p & pymupdf.PDF_PERM_PRINT), "copiar": bool(p & pymupdf.PDF_PERM_COPY),
            "modificar": bool(p & pymupdf.PDF_PERM_MODIFY), "comentar": bool(p & pymupdf.PDF_PERM_ANNOTATE)}
        # Con cifrado, solo la contraseña de propietario (bit 4) da permiso total.
        self.read_only = encrypted and not owner and not (p & pymupdf.PDF_PERM_MODIFY)
        self.signed = bool(self._doc.get_sigflags() > 0)
        self.scrub_metadata = False
        self.pages.locked = self.read_only
        self._undo.clear()
        self._redo.clear()
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
            QTimer.singleShot(0, self._first_layout)

    def _first_layout(self):
        self._layout_split()
        self.fit_width()

    def _layout_split(self):
        """Reparte el ancho: miniaturas (2 columnas si cabe), vista previa y panel de censura."""
        total = max(self.split.width(), 600)
        panel = 320 if self.censor.isVisible() else 0
        pages_w = min(max(int(total * 0.3), THUMB * 2 + 80), total // 2)
        self.split.setSizes([pages_w, max(200, total - pages_w - panel), panel])

    def closeEvent(self, e):
        if self._doc is not None:
            self._doc.close()
        super().closeEvent(e)

    def _on_order_changed(self):
        self._renumber()
        self._set_modified(True)

    def _renumber(self):
        with_marks = {m.page for m in self.marks}
        for i in range(self.pages.count()):
            it = self.pages.item(i)
            orig = it.data(ROLE_PAGE) + 1
            text = str(i + 1) if orig == i + 1 else f"{i + 1}  (era {orig})"
            it.setText(("■ " + text) if orig - 1 in with_marks else text)
            it.setToolTip(f"Posición {i + 1} · página original {orig}")

    def position_of_pages(self) -> dict[int, int]:
        """``{índice_original: posición_actual}`` de las páginas que siguen en el documento."""
        return {self.pages.item(i).data(ROLE_PAGE): i for i in range(self.pages.count())}

    def go_to_page(self, orig: int):
        for i in range(self.pages.count()):
            if self.pages.item(i).data(ROLE_PAGE) == orig:
                if self.pages.currentRow() != i:
                    self.pages.setCurrentRow(i)
                self.pages.scrollToItem(self.pages.item(i))
                return

    # ------------------------------------------------------------ vista previa
    def _render_matrix(self, orig: int, pending: int) -> tuple[pymupdf.Matrix, pymupdf.Matrix]:
        """Matriz de render y matriz 'sin rotar → píxel' para la página mostrada."""
        page = self._doc[orig]
        m = pymupdf.Matrix(self.zoom, self.zoom).prerotate(pending)
        t = page.rotation_matrix * m
        bbox = pymupdf.Rect(0, 0, page.cropbox.width, page.cropbox.height) * t
        t = t * pymupdf.Matrix(1, 0, 0, 1, -bbox.x0, -bbox.y0)
        return m, t

    def _render_redacted(self, orig: int, m: pymupdf.Matrix) -> pymupdf.Pixmap:
        """La página como quedará: se aplican las censuras sobre una copia en memoria."""
        tmp = pymupdf.open()
        try:
            tmp.insert_pdf(self._doc, from_page=orig, to_page=orig)
            page = tmp[0]
            for mk in self.marks:
                if mk.page == orig and mk.kind == "redact":
                    page.add_redact_annot(pymupdf.Rect(mk.rect), fill=(0, 0, 0))
            page.apply_redactions()
            return page.get_pixmap(matrix=m, alpha=False)
        finally:
            tmp.close()

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
        result = self.preview_result and any(mk.page == orig and mk.kind == "redact" for mk in self.marks)
        try:
            pix = self._render_redacted(orig, m) if result else self._doc[orig].get_pixmap(matrix=m, alpha=False)
        except Exception:
            pix, result = self._doc[orig].get_pixmap(matrix=m, alpha=False), False
        marks = []
        selected = {id(x) for x in self.selected_marks}
        for mk in self.marks:
            if mk.page == orig:
                r = pymupdf.Rect(mk.rect) * t
                img = QPixmap(mk.image).transformed(QTransform().rotate(pending)) if mk.image else None
                if mk.kind == "redact":
                    kind = "outline" if result else ("redact-texto" if mk.origin == "texto" else "redact")
                else:
                    kind = mk.kind
                marks.append((kind, QRectF(r.x0, r.y0, r.width, r.height), img, id(mk) in selected))
        self.view.set_page(_to_qpixmap(pix), marks)
        extra = "  ·  vista del resultado final" if result else ""
        self.page_label.setText(f"Página {self.pages.row(it) + 1} de {self.pages.count()}  ·  "
                                f"{int(self.zoom * 100)} %{extra}")

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

    # ------------------------------------------------------------ panel de censura
    def show_censor_panel(self, draw: bool = False):
        if not self.can_edit():
            return False
        if not self.censor.isVisible():
            self.censor.show()
            self._layout_split()
        self.censor.refresh()
        if draw:
            self.btn_redact.setChecked(True)
        else:
            self.censor.terms.setFocus()
        return True

    def hide_censor_panel(self):
        self.btn_redact.setChecked(False)
        self.preview_result = False
        self.censor.result_view.setChecked(False)
        self.selected_marks = []
        self.censor.hide()
        self.show_preview()

    def search_and_mark(self, terms: list[str], regex: bool) -> tuple[int, int, str]:
        """Busca los textos y los agrega como zonas pendientes. Devuelve (encontradas, nuevas, páginas)."""
        hits = core.find_text_labeled(self._source, terms, regex=regex, password=self.password)
        total = sum(len(v) for v in hits.values())
        new = self.add_text_redactions(hits)
        pos = self.position_of_pages()
        pages = ", ".join(str(pos[p] + 1) for p in sorted(hits, key=lambda p: pos.get(p, 10**6)) if p in pos)
        if hits:
            first = min((p for p in hits if p in pos), key=lambda p: pos[p], default=None)
            if first is not None:
                self.go_to_page(first)
        return total, new, pages or "—"

    def select_marks(self, marks: list[Mark]):
        self.selected_marks = list(marks)
        self.show_preview()

    # ------------------------------------------------------------ zonas y firmas
    def _set_mode(self, mode: str | None):
        if mode and not self.can_edit():
            for b in (self.btn_redact, self.btn_sign):
                b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(False)
            self.censor.sync_draw(False)
            return
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
        self.censor.sync_draw(mode == "redact")
        if mode == "redact" and not self.censor.isVisible():
            self.show_censor_panel()
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
        self.push_undo("dibujar zona" if kind == "redact" else "insertar firma")
        self.marks.append(Mark(kind, self._preview_page, tuple(pr),
                               self.signature_image if kind == "image" else None))
        self._set_modified(True)
        self.show_preview()

    def undo_mark(self):
        for i in range(len(self.marks) - 1, -1, -1):
            if self.marks[i].page == self._preview_page:
                self.remove_marks([self.marks[i]])
                return

    def _order_or_rotation_changed(self) -> bool:
        return any(self.pages.item(i).data(ROLE_PAGE) != i or self.pages.item(i).data(ROLE_ROT)
                   for i in range(self.pages.count())) or self.pages.count() != len(self._thumbs)

    def can_edit(self) -> bool:
        if self.read_only:
            self.status.emit("Documento con restricciones: use Seguridad → Desbloquear con la contraseña de permisos")
            return False
        return True

    # ------------------------------------------------------------ deshacer / rehacer
    def _state(self):
        items = [(self.pages.item(i).data(ROLE_PAGE), self.pages.item(i).data(ROLE_ROT))
                 for i in range(self.pages.count())]
        return items, copy.deepcopy(self.marks), self._modified

    def push_undo(self, label: str = "cambio"):
        self._undo.append((self._state(), label))
        del self._undo[:-MAX_UNDO]
        self._redo.clear()
        self._file_redo.clear()
        self.history_changed.emit()

    def _restore(self, state, modified: bool | None = None):
        items, marks, was_modified = state
        cur = self.pages.currentRow()
        self.pages.blockSignals(True)
        self.pages.clear()
        for orig, rot in items:
            pm = self._thumbs[orig].transformed(QTransform().rotate(rot)) if rot else self._thumbs[orig]
            it = QListWidgetItem(QIcon(pm), "")
            it.setData(ROLE_PAGE, orig)
            it.setData(ROLE_ROT, rot)
            it.setTextAlignment(Qt.AlignHCenter)
            self.pages.addItem(it)
        self.pages.blockSignals(False)
        self.marks = copy.deepcopy(marks)
        self.selected_marks = []
        self._renumber()
        self.pages.setCurrentRow(max(0, min(cur, self.pages.count() - 1)))
        self._set_modified(was_modified if modified is None else modified)
        self.show_preview()

    def undo_text(self) -> str:
        if self._undo:
            return self._undo[-1][1]
        if self._file_undo:
            return self._file_undo[-1][4]
        return ""

    def redo_text(self) -> str:
        if self._redo:
            return self._redo[-1][1]
        if self._file_redo:
            return self._file_redo[-1][4]
        return ""

    def _differs_from_disk(self) -> bool:
        try:
            return self._source.resolve() != self.path.resolve() and \
                self._source.read_bytes() != self.path.read_bytes()
        except OSError:
            return True

    def _jump_version(self, from_stack: list, to_stack: list):
        """Cambia a otra versión guardada conservando su historial de cambios pendientes."""
        snap, state, undo, redo, label = from_stack.pop()
        to_stack.append((_snapshot(self._source), self._state(), list(self._undo), list(self._redo), label))
        self._source = snap
        self.reload(from_disk=False)
        self._undo, self._redo = undo, redo
        self._restore(state, modified=state[2] or self._differs_from_disk())

    def undo(self) -> bool:
        if self._undo:
            state, label = self._undo.pop()
            self._redo.append((self._state(), label))
            self._restore(state)
            return True
        if self._file_undo:
            self._jump_version(self._file_undo, self._file_redo)
            self.status.emit("Se volvió a la versión anterior al guardado (aún no se ha escrito en el disco: "
                             "guarde para conservarla).")
            return True
        return False

    def redo(self) -> bool:
        if self._redo:
            state, label = self._redo.pop()
            self._undo.append((self._state(), label))
            self._restore(state)
            return True
        if self._file_redo:
            self._jump_version(self._file_redo, self._file_undo)
            return True
        return False

    # ------------------------------------------------------------ zonas: quitar
    def _mark_menu(self, index: int, global_pos):
        from PySide6.QtWidgets import QMenu
        page_marks = [m for m in self.marks if m.page == self._preview_page]
        m = QMenu(self)
        if 0 <= index < len(page_marks):
            mk = page_marks[index]
            label = "firma" if mk.kind == "image" else f"zona censurada ({mk.origin})"
            m.addAction(f"Quitar esta {label}", lambda: self.remove_marks([mk]))
        if page_marks:
            m.addAction("Quitar todas las marcas de esta página", lambda: self.remove_marks(page_marks))
        if self.marks:
            m.addAction("Quitar todas las zonas censuradas del documento",
                        lambda: self.remove_marks([x for x in self.marks if x.kind == "redact"]))
        m.addSeparator()
        m.addAction("Abrir el panel de censura", self.show_censor_panel)
        m.exec(global_pos)

    def remove_marks(self, marks):
        if not marks:
            return
        self.push_undo("quitar zonas" if len(marks) > 1 else "quitar zona")
        ids = {id(x) for x in marks}
        self.marks = [x for x in self.marks if id(x) not in ids]
        self.selected_marks = [x for x in self.selected_marks if id(x) not in ids]
        self._set_modified(bool(self.marks) or self._order_or_rotation_changed())
        self.show_preview()

    def add_text_redactions(self, hits: dict[int, list]) -> int:
        """Agrega como zonas pendientes los resultados de una búsqueda (índices de página originales).

        Acepta ``{pag: [rect, ...]}`` o ``{pag: [(rect, texto), ...]}``.
        """
        if not self.can_edit():
            return 0
        rects = []
        for p, rs in hits.items():
            for r in rs:
                if len(r) == 2 and not isinstance(r[0], (int, float)):
                    rects.append((p, tuple(r[0]), r[1]))
                else:
                    rects.append((p, tuple(r), ""))
        known = {(m.page, tuple(round(v, 1) for v in m.rect)) for m in self.marks if m.kind == "redact"}
        new = [(p, r, t) for p, r, t in rects if (p, tuple(round(v, 1) for v in r)) not in known]
        if not new:
            return 0
        self.push_undo("censurar por texto")
        for p, r, t in new:
            self.marks.append(Mark("redact", p, r, origin="texto", label=t))
        self._set_modified(True)
        self.show_preview()
        return len(new)

    # ------------------------------------------------------------ ediciones de páginas
    def selected_items(self) -> list[QListWidgetItem]:
        return sorted(self.pages.selectedItems(), key=self.pages.row)

    def rotate_selected(self, degrees: int) -> bool:
        if not self.can_edit():
            return True
        items = self.selected_items()
        if items:
            self.push_undo("rotar páginas")
        for it in items:
            rot = (it.data(ROLE_ROT) + degrees) % 360
            it.setData(ROLE_ROT, rot)
            it.setIcon(QIcon(self._thumbs[it.data(ROLE_PAGE)].transformed(QTransform().rotate(rot))))
        if items:
            self._set_modified(True)
            self.show_preview()
        return bool(items)

    def delete_selected(self) -> int:
        if not self.can_edit():
            return -2
        items = self.selected_items()
        if len(items) >= self.pages.count():
            return -1
        if items:
            self.push_undo("eliminar páginas")
        for it in items:
            self.pages.takeItem(self.pages.row(it))
        if items:
            self._renumber()
            self._set_modified(True)
        return len(items)

    def move_selected(self, where: str | int):
        if not self.can_edit():
            return
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
        out = core.reorder(self._source, output, order, password=self.password)
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
            core.redact(out, out, areas=areas, remove_metadata=self.scrub_metadata, password=self.password)
        if images:
            core.insert_images(out, out, images, password=self.password)
        return out

    def materialize(self) -> Path:
        """Ruta con el contenido actual: el original o una copia temporal con los cambios."""
        if not self._modified:
            return self._source
        tmp = Path(tempfile.mkdtemp(prefix="pdftaller_")) / self.path.name
        return self.write_to(tmp)

    def save(self, output: str | Path | None = None) -> Path:
        label = "guardar"
        if self.has_redactions:
            label = "aplicar censura"
        before = (_snapshot(self._source), self._state(), list(self._undo), list(self._redo), label)
        out = self.write_to(output or self.path)
        self.path = Path(out)
        self.reload()
        self._file_undo.append(before)
        del self._file_undo[:-20]
        self._file_redo.clear()
        if self.censor.isVisible():
            self.censor.refresh()
        self.history_changed.emit()
        return self.path

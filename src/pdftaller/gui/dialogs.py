"""Diálogos de las operaciones de Ordenar y Seguridad."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QRadioButton,
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
    """Contraseña para ABRIR (opcional) + restricciones, con contraseña de PERMISOS (o una generada)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Proteger PDF")
        self.setMinimumWidth(560)
        self.generated = False
        self.c_open = QCheckBox("Pedir contraseña para abrir el documento")
        self.user = QLineEdit(echoMode=QLineEdit.Password)
        self.user_confirm = QLineEdit(echoMode=QLineEdit.Password)
        self.owner = QLineEdit(echoMode=QLineEdit.Password)
        self.owner.setPlaceholderText("Vacía = se genera una automáticamente")
        self.owner_confirm = QLineEdit(echoMode=QLineEdit.Password)
        gen = QPushButton("Generar")
        gen.setToolTip("Crea una contraseña de permisos aleatoria y fuerte")
        gen.clicked.connect(self._generate)
        self.show_pw = QCheckBox("Mostrar")
        self.show_pw.toggled.connect(self._show)
        self.c_print = QCheckBox("Imprimir")
        self.c_print.setChecked(True)
        self.c_copy = QCheckBox("Copiar texto e imágenes")
        self.c_modify = QCheckBox("Modificar (mover, eliminar, editar páginas)")
        self.c_annot = QCheckBox("Comentarios y rellenar formularios")
        self.c_open.toggled.connect(self._toggle)
        self._toggle(False)

        form = QFormLayout(self)
        form.addRow(QLabel("<b>1. Apertura</b> (opcional)"))
        form.addRow(self.c_open)
        form.addRow("Contraseña para abrir:", self.user)
        form.addRow("Repetir:", self.user_confirm)
        form.addRow(_wlabel("<b>2. Permisos</b> — quien abra el documento (con la contraseña de apertura o "
                            "sin contraseña) podrá:"))
        for c in (self.c_print, self.c_copy, self.c_modify, self.c_annot):
            form.addRow(c)
        form.addRow(_wlabel("<b>3. Contraseña de permisos</b> (propietario): quien la use NO tiene restricciones; "
                            "solo sirve para desbloquear. Si la deja vacía se genera una y se le muestra al "
                            "final para que la guarde."))
        form.addRow("Contraseña de permisos:", _row(self.owner, gen, self.show_pw))
        form.addRow("Repetir:", self.owner_confirm)
        form.addRow(_wlabel("<small>Cifrado AES-256. Adobe Acrobat/Reader y PDF Taller aplican las restricciones. "
                            "Los visores de los navegadores (Edge, Chrome, Firefox) pueden ignorar algunas "
                            "(sobre todo copiar e imprimir): para material sensible combine con contraseña "
                            "de apertura y censura.</small>"))
        form.addRow(_buttons(self, "Proteger"))

    def _toggle(self, on: bool):
        self.user.setEnabled(on)
        self.user_confirm.setEnabled(on)

    def _show(self, on: bool):
        mode = QLineEdit.Normal if on else QLineEdit.Password
        for w in (self.user, self.user_confirm, self.owner, self.owner_confirm):
            w.setEchoMode(mode)

    def _generate(self):
        pw = core.generate_password()
        self.owner.setText(pw)
        self.owner_confirm.setText(pw)
        self.show_pw.setChecked(True)
        self.generated = True

    def _restricted(self) -> bool:
        return not all(c.isChecked() for c in (self.c_print, self.c_copy, self.c_modify, self.c_annot))

    def accept(self):
        if self.c_open.isChecked():
            if not self.user.text():
                return QMessageBox.warning(self, "Proteger", "Escriba la contraseña para abrir.")
            if self.user.text() != self.user_confirm.text():
                return QMessageBox.warning(self, "Proteger", "Las contraseñas para abrir no coinciden.")
        elif not self._restricted():
            return QMessageBox.warning(self, "Proteger", "No hay nada que proteger: active la contraseña de "
                                       "apertura o quite al menos un permiso.")
        if self.owner.text() != self.owner_confirm.text():
            return QMessageBox.warning(self, "Proteger", "Las contraseñas de permisos no coinciden.")
        if self.owner.text() and self.c_open.isChecked() and self.owner.text() == self.user.text():
            return QMessageBox.warning(self, "Proteger",
                                       "La contraseña de permisos debe ser distinta de la de apertura;\n"
                                       "si son iguales, quien abra el documento no tendrá restricciones.")
        if not self.owner.text() and self._restricted():
            self._generate()
        super().accept()

    def options(self) -> dict:
        return dict(
            user_password=self.user.text() if self.c_open.isChecked() else "",
            owner_password=self.owner.text() or None,
            allow_print=self.c_print.isChecked(),
            allow_copy=self.c_copy.isChecked(),
            allow_modify=self.c_modify.isChecked(),
            allow_annotate=self.c_annot.isChecked(),
        )


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


def _wlabel(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    return lab


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


class SignDialog(QDialog):
    """Firma digital con certificado .p12/.pfx."""

    def __init__(self, page_label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Firmar digitalmente")
        self.setMinimumWidth(600)
        self.cert = QLineEdit()
        self.cert.setPlaceholderText("Archivo de certificado .p12 / .pfx")
        pick = QPushButton("…")
        pick.clicked.connect(self._pick)
        create = QPushButton("Crear mi certificado…")
        create.clicked.connect(self._create)
        self.pw = QLineEdit(echoMode=QLineEdit.Password)
        export = QPushButton("Exportar certificado público (.cer)…")
        export.setToolTip("Comparta este archivo (no contiene su llave) para que otros validen sus firmas")
        export.clicked.connect(self._export)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Ej.: Apruebo el contenido del acta")
        self.location = QLineEdit()
        self.contact = QLineEdit()
        self.contact.setPlaceholderText("Correo o teléfono (opcional)")
        self.visible = QCheckBox(f"Mostrar un sello visible en {page_label} (abajo a la derecha)")
        self.visible.setChecked(True)
        self.image = QLineEdit()
        self.image.setPlaceholderText("Opcional: imagen de su firma manuscrita (PNG/JPG)")
        pick_img = QPushButton("…")
        pick_img.clicked.connect(self._pick_image)
        self.visible.toggled.connect(lambda on: (self.image.setEnabled(on), pick_img.setEnabled(on)))
        self.lock = QCheckBox("Bloquear el documento: cualquier cambio posterior se marcará como violación")
        self.lock.setChecked(True)
        self.tsa = QCheckBox("Agregar sello de tiempo de un tercero (necesita internet)")
        self.tsa.setToolTip("Un servidor de sellado de tiempo (RFC 3161) certifica la fecha y hora de la firma;\n"
                            "así no depende del reloj de este equipo.")
        self.tsa_url = QLineEdit(core.DEFAULT_TSA)
        self.tsa.toggled.connect(self.tsa_url.setEnabled)
        self.tsa_url.setEnabled(False)
        form = QFormLayout(self)
        form.addRow(_wlabel(
            "La firma digital sella el documento con su certificado: si alguien cambia algo después, la "
            "verificación (aquí, en Adobe Reader o en otros lectores) lo detecta. Hágalo como último paso, "
            "después de censurar."))
        form.addRow("Certificado:", _row(self.cert, pick, create))
        form.addRow("Contraseña del certificado:", self.pw)
        form.addRow("", export)
        form.addRow("Motivo:", self.reason)
        form.addRow("Lugar:", self.location)
        form.addRow("Contacto:", self.contact)
        form.addRow(self.visible)
        form.addRow("Firma manuscrita:", _row(self.image, pick_img))
        form.addRow(QLabel("<b>Seguridad</b>"))
        form.addRow(self.lock)
        form.addRow(self.tsa)
        form.addRow("Servidor de sellado:", self.tsa_url)
        form.addRow(_buttons(self, "Firmar"))

    def _pick(self):
        p, _ = QFileDialog.getOpenFileName(self, "Certificado", "", "Certificados (*.p12 *.pfx)")
        if p:
            self.cert.setText(p)

    def _pick_image(self):
        p, _ = QFileDialog.getOpenFileName(self, "Imagen de la firma", "", "Imágenes (*.png *.jpg *.jpeg *.bmp)")
        if p:
            self.image.setText(p)

    def _create(self):
        dlg = CertificateDialog(self)
        if dlg.exec() and dlg.path:
            self.cert.setText(str(dlg.path))
            self.pw.setText(dlg.password)

    def _export(self):
        if not self.cert.text() or not Path(self.cert.text()).exists():
            return QMessageBox.warning(self, "Exportar", "Elija primero su certificado y escriba su contraseña.")
        out, _ = QFileDialog.getSaveFileName(self, "Guardar certificado público",
                                             str(Path(self.cert.text()).with_suffix(".cer")),
                                             "Certificado público (*.cer)")
        if not out:
            return
        try:
            path, fp = core.export_public_certificate(self.cert.text(), self.pw.text(), out)
        except core.PdfTallerError as exc:
            return QMessageBox.warning(self, "Exportar", str(exc))
        _info_copy(self, "Exportar", f"Certificado público guardado en:\n{path}\n\nHuella SHA-256 (dígala por "
                   f"teléfono o en persona a quien lo reciba, para que la compare):\n{fp}", fp)

    def accept(self):
        if not self.cert.text() or not Path(self.cert.text()).exists():
            return QMessageBox.warning(self, "Firmar", "Elija un certificado o cree uno.")
        if self.visible.isChecked() and self.image.text() and not Path(self.image.text()).exists():
            return QMessageBox.warning(self, "Firmar", "No se encuentra la imagen de la firma.")
        super().accept()

    def options(self) -> dict:
        return dict(reason=self.reason.text(), location=self.location.text(), contact=self.contact.text(),
                    lock=self.lock.isChecked(),
                    signature_image=(self.image.text() or None) if self.visible.isChecked() else None,
                    timestamp_url=self.tsa_url.text().strip() if self.tsa.isChecked() else None)


class CertificateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: Path | None = None
        self.password = ""
        self.setWindowTitle("Crear certificado personal")
        self.name = QLineEdit()
        self.org = QLineEdit()
        self.email = QLineEdit()
        self.pw = QLineEdit(echoMode=QLineEdit.Password)
        self.pw2 = QLineEdit(echoMode=QLineEdit.Password)
        self.strength = QLabel()
        self.pw.textChanged.connect(self._check)
        form = QFormLayout(self)
        form.addRow(_wlabel("Crea un certificado propio (autofirmado, RSA 3072 bits) para firmar documentos "
                            "internos. Para firmas con validez legal use el certificado de una entidad "
                            "certificadora. Guarde el archivo .p12 en un lugar seguro: es su llave para firmar."))
        form.addRow("Nombre completo:", self.name)
        form.addRow("Organización:", self.org)
        form.addRow("Correo:", self.email)
        form.addRow("Contraseña:", self.pw)
        form.addRow("", self.strength)
        form.addRow("Repetir:", self.pw2)
        form.addRow(_buttons(self, "Crear"))
        self._check("")

    def _check(self, text: str):
        try:
            core.check_password_strength(text)
            self.strength.setText("<span style='color:#1a7f37'>✔ Contraseña robusta</span>")
        except core.PdfTallerError:
            self.strength.setText("<small>Mínimo 8 caracteres combinando 3 de: minúsculas, mayúsculas, "
                                  "números y símbolos.</small>")

    def accept(self):
        if self.pw.text() != self.pw2.text():
            return QMessageBox.warning(self, "Certificado", "Las contraseñas no coinciden.")
        try:
            core.check_password_strength(self.pw.text())
        except core.PdfTallerError as exc:
            return QMessageBox.warning(self, "Certificado", str(exc))
        out, _ = QFileDialog.getSaveFileName(self, "Guardar certificado",
                                             f"{self.name.text().strip() or 'certificado'}.p12",
                                             "Certificado (*.p12)")
        if not out:
            return
        try:
            self.path = core.create_certificate(out, self.name.text(), self.pw.text(),
                                                email=self.email.text() or None,
                                                organization=self.org.text() or None)
            # El certificado propio es de confianza en este equipo; se exporta su parte pública.
            cer, fp = core.export_public_certificate(self.path, self.pw.text(), Path(out).with_suffix(".cer"))
            core.trust_certificate(cer)
        except core.PdfTallerError as exc:
            return QMessageBox.warning(self, "Certificado", str(exc))
        self.password = self.pw.text()
        _info_copy(self, "Certificado", f"Certificado creado:\n{self.path}\n\nParte pública para compartir:\n{cer}\n\n"
                   f"Huella SHA-256:\n{fp}", fp)
        super().accept()


def _info_copy(parent, title: str, text: str, to_copy: str):
    """Mensaje con un botón para copiar un valor (huella, contraseña)."""
    box = QMessageBox(QMessageBox.Information, title, text, QMessageBox.Ok, parent)
    copy_btn = box.addButton("Copiar", QMessageBox.ActionRole)
    box.setTextInteractionFlags(Qt.TextSelectableByMouse)
    while True:
        box.exec()
        if box.clickedButton() is copy_btn:
            QGuiApplication.clipboard().setText(to_copy)
            box.setInformativeText("✔ Copiado al portapapeles.")
            continue
        break


class CompressDialog(QDialog):
    def __init__(self, source: Path, password: str | None, parent=None):
        super().__init__(parent)
        self.source, self.password = source, password
        self.setWindowTitle("Comprimir PDF")
        self.setMinimumWidth(560)
        self.levels: dict[str, QRadioButton] = {}
        self.texts = {"baja": "Baja — sin pérdida (limpia el archivo y recorta fuentes)",
                      "media": "Media — imágenes a 150 ppp, buena para imprimir",
                      "alta": "Alta — imágenes a 96 ppp, la más pequeña, para correo o web",
                      "personalizada": "Personalizada:"}
        lay = QVBoxLayout(self)
        self.analysis = QLabel()
        self.analysis.setWordWrap(True)
        self.analysis.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.analysis.setStyleSheet("background:#f3f4f6; padding:6px; border-radius:4px")
        lay.addWidget(self.analysis)
        lay.addWidget(QLabel("<b>Nivel de compresión</b>"))
        grp = QButtonGroup(self)
        for key, text in self.texts.items():
            r = QRadioButton(text)
            grp.addButton(r)
            self.levels[key] = r
            lay.addWidget(r)
        self.dpi = QSpinBox()
        self.dpi.setRange(36, 600)
        self.dpi.setValue(120)
        self.dpi.setSuffix(" ppp")
        self.quality = QSpinBox()
        self.quality.setRange(10, 100)
        self.quality.setValue(70)
        self.quality.setPrefix("calidad JPEG ")
        custom = QHBoxLayout()
        custom.addSpacing(24)
        custom.addWidget(QLabel("Resolución de imágenes:"))
        custom.addWidget(self.dpi)
        custom.addWidget(self.quality)
        custom.addStretch()
        lay.addLayout(custom)
        for w in (self.dpi, self.quality):
            w.valueChanged.connect(lambda *_: self.levels["personalizada"].setChecked(True))
        self.gray = QCheckBox("Convertir las imágenes a escala de grises")
        self.strip = QCheckBox("Quitar metadatos, adjuntos y JavaScript")
        lay.addWidget(self.gray)
        lay.addWidget(self.strip)
        est = QPushButton("Calcular tamaño de cada nivel")
        est.clicked.connect(self._estimate)
        lay.addWidget(est)
        lay.addWidget(_buttons(self, "Comprimir"))
        try:
            a = core.analyze(source, password)
            self.analysis.setText(escape(a.message()).replace("\n", "<br>"))
            self.levels[a.recommendation()].setChecked(True)
        except core.PdfTallerError as exc:
            self.analysis.setText(escape(str(exc)))
            self.levels["media"].setChecked(True)

    def _estimate(self):
        from .worker import run_busy
        try:
            sizes = run_busy(self, "Comprimir", "Calculando tamaños…", core.estimate_compression,
                             self.source, password=self.password, gray=self.gray.isChecked(),
                             strip=self.strip.isChecked())
            sizes["personalizada"] = run_busy(self, "Comprimir", "Calculando tamaños…", self._custom_size)
        except core.PdfTallerError as exc:
            return QMessageBox.warning(self, "Comprimir", str(exc))
        before = self.source.stat().st_size
        for k, r in self.levels.items():
            n = sizes.get(k)
            if n is not None:
                pct = 100 * (1 - n / before) if before else 0
                r.setText(f"{self.texts[k]}   →  {_size(n)} (−{max(pct, 0):.0f} %)")

    def _custom_size(self) -> int:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            return core.compress(self.source, Path(tmp) / "c.pdf", **self.options()).after

    def level(self) -> str:
        k = next(k for k, r in self.levels.items() if r.isChecked())
        return "media" if k == "personalizada" else k

    def options(self) -> dict:
        custom = self.levels["personalizada"].isChecked()
        return dict(level=self.level(), gray=self.gray.isChecked(), strip=self.strip.isChecked(),
                    dpi=self.dpi.value() if custom else None, quality=self.quality.value() if custom else None,
                    password=self.password)


def _size(n: int) -> str:
    return f"{n / 1_048_576:.2f} MB" if n >= 1_048_576 else f"{n / 1024:.0f} KB"


class OcrDialog(QDialog):
    def __init__(self, languages: list[str], parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QComboBox
        self.setWindowTitle("Reconocer texto (OCR)")
        self.lang = QComboBox()
        names = {"spa": "Español", "eng": "Inglés", "por": "Portugués", "fra": "Francés", "deu": "Alemán"}
        options = []
        if "spa" in languages and "eng" in languages:
            options.append(("spa+eng", "Español + Inglés"))
        options += [(l, names.get(l, l)) for l in languages]
        for code, label in options:
            self.lang.addItem(label, code)
        self.only = QCheckBox("Solo páginas escaneadas (sin texto)")
        self.only.setChecked(True)
        self.keep = QCheckBox("Conservar la página original y agregar el texto invisible encima (recomendado)")
        self.keep.setChecked(True)
        self.keep.setToolTip("Sin pérdida de calidad y el archivo casi no crece.\n"
                             "Desmarcado: cada página se reemplaza por una imagen nueva con el texto.")
        self.dpi = QSpinBox()
        self.dpi.setRange(150, 600)
        self.dpi.setValue(300)
        self.dpi.setSuffix(" ppp")
        form = QFormLayout(self)
        form.addRow(_wlabel("Convierte páginas escaneadas en texto que se puede buscar, copiar y censurar."))
        form.addRow("Idioma:", self.lang)
        form.addRow("Resolución de lectura:", self.dpi)
        form.addRow(self.only)
        form.addRow(self.keep)
        form.addRow(_buttons(self, "Reconocer"))


class SignaturesDialog(QDialog):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(f"Firmas digitales de «{path.name}»")
        self.resize(720, 460)
        self.out = QTextBrowser()
        self.out.setOpenLinks(False)
        self.out.anchorClicked.connect(self._link)
        lay = QVBoxLayout(self)
        lay.addWidget(self.out)
        row = QHBoxLayout()
        manage = QPushButton("Certificados de confianza…")
        manage.clicked.connect(lambda: (TrustDialog(self).exec(), self._load()))
        row.addWidget(manage)
        row.addStretch()
        close = QPushButton("Cerrar")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        lay.addLayout(row)
        self._load()

    def _load(self):
        try:
            self.sigs = core.verify_signatures(self.path)
        except Exception as exc:
            self.out.setPlainText(f"No se pudieron verificar las firmas: {exc}")
            return
        if not self.sigs:
            self.out.setHtml("<p>Este documento no tiene firmas digitales.</p>")
            return
        h = []
        for i, s in enumerate(self.sigs):
            ok = s.intact and (s.covers_all or s.changes in ("ninguno", "solo datos de validación"))
            color = "#1a7f37" if ok and s.trusted else ("#b35900" if s.intact else "#b00")
            h.append(f"<h3 style='color:{color}'>{escape(s.summary)}</h3>")
            h.append("<table cellpadding=2>")
            for k, v in [("Firmante", s.signer), ("Emisor", s.issuer + (" (autofirmado)" if s.self_signed else "")),
                         ("Fecha indicada", s.signed_at),
                         ("Sello de tiempo", s.timestamp or "no tiene"),
                         ("Certificado válido", f"{s.valid_from} a {s.valid_until}" + (" — VENCIDO" if s.cert_expired else "")),
                         ("Documento bloqueado", "sí" if s.certified else "no"),
                         ("De confianza", "sí" if s.trusted else "no"),
                         ("Huella SHA-256", s.fingerprint)]:
                h.append(f"<tr><td><b>{k}:</b></td><td><code>{escape(v)}</code></td></tr>" if k == "Huella SHA-256"
                         else f"<tr><td><b>{k}:</b></td><td>{escape(v)}</td></tr>")
            h.append("</table>")
            for d in s.details:
                h.append(f"<p>• {escape(d)}</p>")
            if s.intact and not s.trusted:
                h.append(f"<p><a href='trust:{i}'>Confiar en el certificado de este firmante…</a></p>")
            h.append("<hr>")
        self.out.setHtml("".join(h))

    def _link(self, url):
        if url.scheme() != "trust":
            return
        s = self.sigs[int(url.path())]
        r = QMessageBox.question(
            self, "Confiar en el certificado",
            f"Firmante: {s.signer}\n\nHuella SHA-256:\n{s.fingerprint}\n\n"
            "Compare esta huella con la que le dé el firmante por otro medio (en persona, por teléfono). "
            "Si coincide, sus firmas se mostrarán como verificadas en este equipo.\n\n¿Confiar en este certificado?")
        if r == QMessageBox.Yes:
            core.trust_certificate(core.signer_certificate(self.path, int(url.path())), s.signer)
            self._load()


class TrustDialog(QDialog):
    """Lista de certificados de confianza de este equipo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Certificados de confianza")
        self.resize(640, 320)
        self.list = QListWidget()
        lay = QVBoxLayout(self)
        lay.addWidget(_wlabel("Las firmas hechas con estos certificados se muestran como verificadas. "
                              f"Carpeta: {core.trust_dir()}"))
        lay.addWidget(self.list)
        row = QHBoxLayout()
        add = QPushButton("Importar .cer…")
        add.clicked.connect(self._add)
        rm = QPushButton("Quitar")
        rm.clicked.connect(self._remove)
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch()
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self._load()

    def _load(self):
        from cryptography import x509
        import hashlib
        self.list.clear()
        for p in core.trusted_certificates():
            data = p.read_bytes()
            try:
                c = x509.load_der_x509_certificate(data)
            except ValueError:
                try:
                    c = x509.load_pem_x509_certificate(data)
                except ValueError:
                    continue
            from cryptography.hazmat.primitives.serialization import Encoding
            fp = hashlib.sha256(c.public_bytes(Encoding.DER)).hexdigest().upper()
            fp = ":".join(fp[i:i + 2] for i in range(0, len(fp), 2))
            it = QListWidgetItem(f"{c.subject.rfc4514_string()}\n   huella {fp[:47]}…  ·  vence {c.not_valid_after_utc.date()}")
            it.setData(Qt.UserRole, fp)
            self.list.addItem(it)

    def _add(self):
        p, _ = QFileDialog.getOpenFileName(self, "Certificado público", "", "Certificados (*.cer *.crt *.pem *.der)")
        if p:
            try:
                core.trust_certificate(p)
            except Exception as exc:
                QMessageBox.warning(self, "Importar", f"No es un certificado válido: {exc}")
            self._load()

    def _remove(self):
        it = self.list.currentItem()
        if it and QMessageBox.question(self, "Quitar", "¿Dejar de confiar en este certificado?") == QMessageBox.Yes:
            core.untrust_certificate(it.data(Qt.UserRole))
            self._load()

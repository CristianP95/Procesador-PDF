"""Ejecutar operaciones largas (OCR, compresión, firma con sello de tiempo) sin congelar la ventana."""
from __future__ import annotations

from PySide6.QtCore import QEventLoop, QThread, Qt, Signal
from PySide6.QtWidgets import QProgressDialog, QWidget


class _Worker(QThread):
    progressed = Signal(int, int)

    def __init__(self, fn, args, kwargs, with_progress: bool):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.result = None
        self.error: BaseException | None = None
        self.cancelled = False
        if with_progress:
            self.kwargs["progress"] = self._progress

    def _progress(self, i: int, total: int):
        self.progressed.emit(i, total)
        return not self.cancelled

    def run(self):
        try:
            self.result = self.fn(*self.args, **self.kwargs)
        except BaseException as exc:  # se relanza en el hilo principal
            self.error = exc


def run_busy(parent: QWidget | None, title: str, text: str, fn, *args, progress: bool = False,
             cancellable: bool = False, **kwargs):
    """Ejecuta ``fn(*args, **kwargs)`` en otro hilo mostrando una ventana de progreso.

    Con ``progress=True`` se pasa a ``fn`` un argumento ``progress(i, total)`` que actualiza la barra
    y devuelve ``False`` si el usuario pulsó Cancelar. Relanza la excepción de ``fn`` si la hubo.
    """
    worker = _Worker(fn, args, kwargs, progress)
    dlg = QProgressDialog(text, "Cancelar" if (cancellable or progress) else None, 0, 0, parent)
    dlg.setWindowTitle(title)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(300)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    if not (cancellable or progress):
        dlg.setCancelButton(None)

    def on_progress(i, total):
        dlg.setMaximum(total)
        dlg.setValue(min(i, total))
        dlg.setLabelText(f"{text}\nPágina {min(i + 1, total)} de {total}")

    def on_cancel():
        worker.cancelled = True
        dlg.setLabelText("Cancelando…")

    worker.progressed.connect(on_progress)
    dlg.canceled.connect(on_cancel)
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    worker.start()
    if worker.isRunning():
        loop.exec()
    worker.wait()
    dlg.close()
    dlg.deleteLater()
    if worker.error is not None:
        raise worker.error
    return worker.result

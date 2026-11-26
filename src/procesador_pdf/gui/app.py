import sys

from PySide6.QtWidgets import QApplication

from procesador_pdf import branding

from .about import app_icon
from .main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName(branding.APP_NAME)
    app.setApplicationVersion(branding.VERSION)
    app.setOrganizationName(branding.APP_NAME)
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon())
    if sys.platform == "win32":
        # Icono propio en la barra de tareas (si no, Windows muestra el de Python)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{branding.APP_ID}.{branding.VERSION}")
        except Exception:
            pass
    win = MainWindow()
    for path in argv[1:]:
        win.open_file(path)
    win.show()
    return app.exec()

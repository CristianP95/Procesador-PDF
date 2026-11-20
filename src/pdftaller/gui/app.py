import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("PDF Taller")
    app.setOrganizationName("PDF Taller")
    app.setStyle("Fusion")
    win = MainWindow()
    for path in argv[1:]:
        win.open_file(path)
    win.show()
    return app.exec()

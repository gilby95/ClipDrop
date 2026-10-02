import os
import sys


def main():
    if os.name == "nt":
        try:  # own taskbar icon instead of python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ClipDrop.App")
        except Exception:
            pass
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow
    from .ui.theme import QSS, app_icon

    app = QApplication(sys.argv)
    app.setApplicationName("ClipDrop")
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon())
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

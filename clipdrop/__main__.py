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
    from .ui import theme

    app = QApplication(sys.argv)
    app.setApplicationName("ClipDrop")
    app.setStyle("Fusion")
    theme.init_fonts()
    app.setFont(theme.ui(13))
    app.setStyleSheet(theme.qss())
    app_icon = theme.app_icon
    app.setWindowIcon(app_icon())
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

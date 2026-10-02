"""Writes assets/clipdrop.ico from the logo drawn in code."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PySide6.QtGui import QGuiApplication  # noqa: E402

from clipdrop.ui.theme import draw_logo  # noqa: E402

app = QGuiApplication([])
out = os.path.join(os.path.dirname(__file__), "..", "assets", "clipdrop.ico")
os.makedirs(os.path.dirname(out), exist_ok=True)
if not draw_logo(256).save(out, "ICO"):
    sys.exit("Couldn't write the icon")
print("wrote", os.path.normpath(out))

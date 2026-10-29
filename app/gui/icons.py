import qtawesome as qta
from PySide6.QtWidgets import QApplication


def _brand_icon(name, color):
    if QApplication.instance() is None:
        raise RuntimeError("QApplication must be created before loading brand icons")
    return qta.icon(name, color=color)


def apple_icon(color="#8b919b"):
    return _brand_icon("fa6b.apple", color)


def android_icon(color="#3ddc84"):
    return _brand_icon("fa6b.android", color)


def apple_pixmap(size, color="#8b919b"):
    return apple_icon(color).pixmap(size, size)

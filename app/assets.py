from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def path(name):
    return str(ASSETS / name)


def exists(name):
    return (ASSETS / name).is_file()


def app_icon():
    icon = QIcon()
    for name in ("icon-64.png", "icon.png", "icon-512.png"):
        if exists(name):
            icon.addFile(path(name))
    return icon


def banner_pixmap(width, opacity=1.0):
    pm = QPixmap(path("banner.png"))
    if pm.isNull():
        return QPixmap()
    dpr = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
    pm = pm.scaledToWidth(max(1, int(width * dpr)), Qt.TransformationMode.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    if opacity >= 1.0:
        return pm
    out = QPixmap(pm.size())
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setOpacity(opacity)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out

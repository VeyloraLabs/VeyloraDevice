from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from .. import theme
from .icons import apple_pixmap


def trim_transparent(pm, threshold=24):
    try:
        img = pm.toImage()
        if not img.hasAlphaChannel():
            return pm
        small = img.scaled(160, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        x0, y0, x1, y1 = small.width(), small.height(), -1, -1
        for y in range(small.height()):
            for x in range(small.width()):
                if small.pixelColor(x, y).alpha() > threshold:
                    x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
        if x1 < 0:
            return pm
        k = img.width() / small.width()
        rect = QRect(int((x0 - 1) * k), int((y0 - 1) * k), int((x1 - x0 + 3) * k), int((y1 - y0 + 3) * k))
        rect = rect.intersected(img.rect())
        if rect.width() < 24 or rect.height() < 24:
            return pm
        return pm.copy(rect)
    except Exception:
        return pm


class DeviceImage(QWidget):
    MAX_FRACTION = 0.78

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = None
        self.connected = False
        self.mode = "none"
        self._glow = 0.0
        self._apple_size = 104
        self._apple = apple_pixmap(self._apple_size)
        self.setMinimumSize(260, 340)
        self.anim = QPropertyAnimation(self, b"glow", self)
        self.anim.setDuration(2200)
        self.anim.setStartValue(0.25)
        self.anim.setKeyValueAt(0.5, 1.0)
        self.anim.setEndValue(0.25)
        self.anim.setLoopCount(-1)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutSine)

    def _get_glow(self):
        return self._glow

    def _set_glow(self, v):
        self._glow = v
        self.update()

    glow = Property(float, _get_glow, _set_glow)

    def set_connected(self, connected, mode="none"):
        was, self.connected, self.mode = self.connected, connected, mode
        if connected and not was:
            self.anim.start()
        elif not connected and was:
            self.anim.stop()
            self._glow = 0.0
        self.update()

    def set_pixmap(self, pm):
        self.pixmap = trim_transparent(pm) if (pm is not None and not pm.isNull()) else None
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        box = QRectF(0, 0, w, h)

        if self.connected:
            col = QColor(theme.ACCENT if self.mode == "normal" else theme.WARN)
            g = QRadialGradient(box.center(), min(w, h) * 0.62)
            col.setAlphaF(0.28 * self._glow)
            g.setColorAt(0, col)
            col.setAlphaF(0)
            g.setColorAt(1, col)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(box.center(), min(w, h) * 0.62, min(w, h) * 0.62)

        if self.pixmap is not None:
            dpr = self.devicePixelRatioF() or 1.0
            nat_w = self.pixmap.width() / dpr
            nat_h = self.pixmap.height() / dpr
            scale = min(1.0, box.width() * self.MAX_FRACTION / nat_w, box.height() * self.MAX_FRACTION / nat_h)
            tw, th = nat_w * scale, nat_h * scale
            target = QRectF(box.center().x() - tw / 2, box.center().y() - th / 2, tw, th)
            p.drawPixmap(target, self.pixmap, QRectF(self.pixmap.rect()))
        else:
            p.setOpacity(0.35 + (0.4 * self._glow if self.connected else 0.0))
            sz = self._apple_size
            target = QRectF(box.center().x() - sz / 2, box.center().y() - sz / 2, sz, sz)
            p.drawPixmap(target, self._apple, QRectF(self._apple.rect()))
            p.setOpacity(1)
        p.end()

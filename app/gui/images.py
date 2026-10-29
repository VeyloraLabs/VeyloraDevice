from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from ..core import catalog
from ..dispatch import post


def placeholder(text, size):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(38, 42, 46))
    p.setPen(QColor(60, 66, 72))
    m = size * 0.12
    p.drawRoundedRect(QRectF(m, m, size - 2 * m, size - 2 * m), 14, 14)
    p.setPen(QColor(140, 150, 156))
    f = QFont()
    f.setPixelSize(max(11, size // 7))
    p.setFont(f)
    p.drawText(QRectF(m, m, size - 2 * m, size - 2 * m), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
               text[:14])
    p.end()
    return pm


def fit(pm, size):
    scaled = pm.scaled(QSize(size, size), Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    p.end()
    return canvas


class ImageLoader:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=6)
        self.mem = {}
        self.waiting = {}

    def get(self, url, cb):
        if not url:
            return
        if url in self.mem:
            cb(self.mem[url])
            return
        if url in self.waiting:
            self.waiting[url].append(cb)
            return
        self.waiting[url] = [cb]

        def work():
            try:
                path = catalog.download_image(url)
            except Exception:
                path = None
            post(lambda: self._done(url, path))

        self.pool.submit(work)

    def _done(self, url, path):
        cbs = self.waiting.pop(url, [])
        pm = QPixmap(path) if path else QPixmap()
        if pm.isNull():
            return
        self.mem[url] = pm
        for cb in cbs:
            try:
                cb(pm)
            except RuntimeError:
                pass

    def icon_into(self, item, url, size):
        self.get(url, lambda pm: item.setIcon(QIcon(fit(pm, size))))

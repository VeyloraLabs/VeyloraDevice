from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, CardWidget, ProgressBar, StrongBodyLabel

from .. import i18n, theme

LEVEL_COLORS = {"ok": None, "warn": theme.WARN, "bad": theme.DANGER}


class StatTile(CardWidget):

    def __init__(self, title_es, title_en, parent=None):
        super().__init__(parent)
        self.setBorderRadius(12)
        self.setMinimumHeight(118)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(3)
        self.title = i18n.bind(CaptionLabel(), "setText", title_es, title_en)
        self.title.setStyleSheet(f"color:{theme.MUTED}")
        self.value = StrongBodyLabel("—")
        self._set_value_style(None)
        self.bar = ProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setVisible(False)
        self.detail = CaptionLabel("")
        self.detail.setStyleSheet(f"color:{theme.MUTED}")
        self.detail.setWordWrap(True)
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addWidget(self.bar)
        lay.addWidget(self.detail)
        lay.addStretch(1)

    def _set_value_style(self, color):
        self.value.setStyleSheet(f"font-size:28px; font-weight:700; color:{color or '#f2f4f7'};")

    def set(self, value, percent=None, detail="", level="ok"):
        color = LEVEL_COLORS.get(level)
        self.value.setText(value)
        self._set_value_style(color)
        self.detail.setText(detail)
        self.bar.setVisible(percent is not None)
        if percent is not None:
            bar_color = color or theme.ACCENT
            self.bar.setValue(max(0, min(100, int(percent))))
            self.bar.setCustomBarColor(bar_color, bar_color)

    def clear(self, detail=""):
        self.set("—", None, detail)


class StatStrip(QWidget):

    def __init__(self, titles, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.tiles = []
        for es, en in titles:
            tile = StatTile(es, en)
            row.addWidget(tile, 1)
            self.tiles.append(tile)

    def clear(self):
        for tile in self.tiles:
            tile.clear()

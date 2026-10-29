from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, FluentIcon as FIF, IconWidget, InfoBar,
                            InfoBarPosition, SmoothScrollArea, StrongBodyLabel, SubtitleLabel, TitleLabel)

from .. import i18n, theme


class Page(QWidget):

    def __init__(self, name, title, subtitle, scroll=False, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 18)
        outer.setSpacing(4)
        self.title = i18n.bind(TitleLabel(), "setText", *title)
        self.subtitle = i18n.bind(CaptionLabel(), "setText", *subtitle)
        self.subtitle.setStyleSheet(f"color:{theme.MUTED}")
        outer.addWidget(self.title)
        outer.addWidget(self.subtitle)
        outer.addSpacing(10)
        if scroll:
            area = SmoothScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.enableTransparentBackground()
            inner = QWidget()
            inner.setStyleSheet("background: transparent")
            self.body = QVBoxLayout(inner)
            self.body.setContentsMargins(0, 0, 12, 0)
            self.body.setSpacing(10)
            area.setWidget(inner)
            outer.addWidget(area, 1)
        else:
            self.body = QVBoxLayout()
            self.body.setContentsMargins(0, 0, 0, 0)
            self.body.setSpacing(10)
            outer.addLayout(self.body, 1)


def section(es, en):
    lbl = i18n.bind(StrongBodyLabel(), "setText", es, en)
    lbl.setStyleSheet(f"color:{theme.ACCENT}; padding-top:8px")
    return lbl


class ToolCard(CardWidget):

    def __init__(self, icon, title, desc, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(74)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(14)
        ic = IconWidget(icon)
        ic.setFixedSize(26, 26)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.t = i18n.bind(StrongBodyLabel(), "setText", *title)
        self.d = i18n.bind(CaptionLabel(), "setText", *desc)
        self.d.setStyleSheet(f"color:{theme.MUTED}")
        self.d.setWordWrap(True)
        col.addWidget(self.t)
        col.addWidget(self.d)
        row.addWidget(ic)
        row.addLayout(col, 1)


class Pill(QLabel):

    COLORS = {"ok": (theme.ACCENT, "#06281c"), "warn": (theme.WARN, "#2d1d00"),
              "err": (theme.DANGER, "#2d0a0b"), "muted": ("#3a3f47", "#c9ced6")}

    def __init__(self, text="", kind="muted", parent=None):
        super().__init__(text, parent)
        self.set_kind(kind)

    def set_kind(self, kind):
        bg, fg = self.COLORS.get(kind, self.COLORS["muted"])
        self.setStyleSheet(f"background:{bg}; color:{fg}; border-radius:10px; padding:3px 12px; font-weight:600;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.adjustSize()


class Banner(CardWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        from qfluentwidgets import PrimaryPushButton, PushButton
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)
        self.icon = IconWidget(FIF.INFO)
        self.icon.setFixedSize(28, 28)
        self.msg = BodyLabel()
        self.msg.setWordWrap(True)
        self.msg.setOpenExternalLinks(True)
        self.btn1 = PrimaryPushButton()
        self.btn2 = PushButton()
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.msg, 1)
        lay.addWidget(self.btn1)
        lay.addWidget(self.btn2)
        self.setVisible(False)

    def show_message(self, html, b1=None, b2=None, icon=FIF.INFO):
        self.icon.setIcon(icon)
        self.msg.setText(html)
        for b, t in ((self.btn1, b1), (self.btn2, b2)):
            b.setVisible(bool(t))
            b.setText(t or "")
        self.setVisible(True)


def toast(parent, kind, title, text="", ms=4500):
    fn = {"ok": InfoBar.success, "warn": InfoBar.warning, "err": InfoBar.error}.get(kind, InfoBar.info)
    return fn(title=title, content=text, orient=Qt.Orientation.Horizontal, isClosable=True,
              position=InfoBarPosition.TOP_RIGHT, duration=ms, parent=parent.window())


def card_frame(layout_cls=QVBoxLayout, margins=(18, 14, 18, 14), spacing=8):
    c = CardWidget()
    c.setBorderRadius(12)
    lay = layout_cls(c)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return c, lay

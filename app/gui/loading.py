from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import IndeterminateProgressRing

from .. import theme


class LoadingScreen(QWidget):

    def __init__(self, parent=None):
        flags = Qt.WindowType.Widget
        if parent is None:
            flags = Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
        super().__init__(parent, flags)
        self.setObjectName("loadingScreen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"#loadingScreen {{ background: {theme.BG}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        progress = IndeterminateProgressRing(self)
        progress.setFixedSize(48, 48)
        progress.setStrokeWidth(4)
        layout.addWidget(progress, alignment=Qt.AlignmentFlag.AlignCenter)

        if parent is None:
            self.setFixedSize(104, 104)

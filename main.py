import sys
import time

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

from app import assets, dispatch, osinfo, theme
from app.gui.main_window import MainWindow
from app.gui.loading import LoadingScreen


def migrate_settings():
    new = QSettings()
    if new.allKeys():
        return
    old = QSettings("soyhugo", "Veylora")
    for key in old.allKeys():
        new.setValue(key, old.value(key))


def main():
    osinfo.extend_path()
    osinfo.set_windows_app_id("VeyloraLabs.VeyloraDevice")
    app = QApplication(sys.argv)
    app.setApplicationName("VeyloraDevice")
    app.setOrganizationName("VeyloraLabs")
    app.setDesktopFileName("veyloradevice")
    migrate_settings()
    app.setWindowIcon(assets.app_icon())
    dispatch.init()
    theme.apply(app)
    splash = LoadingScreen()
    screen = app.primaryScreen().availableGeometry()
    splash.move(screen.center() - splash.rect().center())
    splash.show()
    app.processEvents()
    started = time.monotonic()
    win = MainWindow()
    win.showMaximized()
    remaining = max(0, 650 - int((time.monotonic() - started) * 1000))
    QTimer.singleShot(remaining, splash.close)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

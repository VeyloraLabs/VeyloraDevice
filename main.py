import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app import assets, dispatch, theme
from app.gui.main_window import MainWindow


def migrate_settings():
    new = QSettings()
    if new.allKeys():
        return
    old = QSettings("soyhugo", "Veylora")
    for key in old.allKeys():
        new.setValue(key, old.value(key))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("VeyloraDevice")
    app.setOrganizationName("VeyloraLabs")
    app.setDesktopFileName("veyloradevice")
    migrate_settings()
    app.setWindowIcon(assets.app_icon())
    dispatch.init()
    theme.apply(app)
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

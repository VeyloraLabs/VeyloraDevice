import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings


def app_dir():
    return str(Path(__file__).resolve().parents[1])


def default_ipsw_dir():
    local = os.path.join(app_dir(), "IPSW")
    if not getattr(sys, "frozen", False) and os.access(app_dir(), os.W_OK):
        return local
    return str(Path.home() / "Downloads" / "IPSW")


def ipsw_dir():
    stored = QSettings().value("ipsw_dir")
    default = default_ipsw_dir()
    if not stored or (os.path.basename(str(stored)) == "IPSW" and os.path.abspath(str(stored)) != os.path.abspath(default)
                      and not os.path.isdir(str(stored))):
        stored = default
        QSettings().setValue("ipsw_dir", stored)
    return str(stored)


def set_ipsw_dir(d):
    QSettings().setValue("ipsw_dir", d)

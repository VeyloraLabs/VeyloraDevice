import re

import requests
from PySide6.QtCore import QObject, QSettings, QTimer, Signal

from . import __version__
from .dispatch import run_async

REPO = "VeyloraLabs/VeyloraDevice"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
CHECK_EVERY_MS = 6 * 60 * 60 * 1000
FIRST_CHECK_MS = 5000
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": f"VeyloraDevice/{__version__} (VeyloraLabs)"}


def parse_version(text):
    match = re.match(r"\s*v?(\d+(?:\.\d+){0,3})", str(text or ""))
    if not match:
        return None
    parts = [int(p) for p in match.group(1).split(".")]
    return tuple(parts + [0] * (4 - len(parts)))


def is_newer(remote, local):
    remote_v, local_v = parse_version(remote), parse_version(local)
    return bool(remote_v and local_v and remote_v > local_v)


def pick_asset(assets, os_release=None):
    if os_release is None:
        try:
            with open("/etc/os-release", encoding="utf-8") as handle:
                os_release = handle.read().lower()
        except OSError:
            os_release = ""
    names = [(a.get("name", ""), a.get("browser_download_url", "")) for a in assets]
    if re.search(r"debian|ubuntu|mint|pop|elementary|kali", os_release):
        order = (".deb", ".appimage", ".tar.gz")
    elif re.search(r"fedora|rhel|centos|rocky|alma|suse|mageia", os_release):
        order = (".rpm", ".appimage", ".tar.gz")
    else:
        order = (".appimage", ".tar.gz", ".deb", ".rpm")
    for extension in order:
        for name, url in names:
            if name.lower().endswith(extension) and url:
                return name, url
    return None


def parse_release(data):
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name") or ""
    if not parse_version(tag):
        return None
    return {
        "version": tag.lstrip("vV"),
        "tag": tag,
        "name": data.get("name") or tag,
        "notes": (data.get("body") or "").strip(),
        "url": data.get("html_url") or RELEASES_URL,
        "asset": pick_asset(data.get("assets") or []),
    }


def fetch_latest():
    response = requests.get(API_LATEST, headers=HEADERS, timeout=8)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return parse_release(response.json())


def auto_enabled():
    return str(QSettings().value("update/auto", "true")).lower() in ("true", "1")


def set_auto(value):
    QSettings().setValue("update/auto", bool(value))


def skipped_version():
    return str(QSettings().value("update/skip", ""))


def skip_version(version):
    QSettings().setValue("update/skip", version)


class UpdateChecker(QObject):
    found = Signal(dict)
    finished = Signal(object, str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._announced = set()
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_EVERY_MS)
        self._timer.timeout.connect(lambda: self.check(False))

    def start(self):
        self._timer.start()
        QTimer.singleShot(FIRST_CHECK_MS, lambda: self.check(False))

    def check(self, manual=True):
        if self._busy or (not manual and not auto_enabled()):
            return
        self._busy = True

        def done(release):
            self._busy = False
            newer = bool(release and is_newer(release["version"], __version__))
            self.finished.emit(release, "", manual)
            if not newer:
                return
            if manual or (release["version"] != skipped_version() and release["version"] not in self._announced):
                self._announced.add(release["version"])
                self.found.emit(release)

        def failed(error):
            self._busy = False
            self.finished.emit(None, str(error), manual)

        run_async(fetch_latest, done, failed)

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests
from PySide6.QtCore import QObject, QSettings, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from . import __version__, osinfo
from .dispatch import run_async

REPO = "VeyloraLabs/VeyloraDevice"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
CHECK_EVERY_MS = 30 * 60 * 1000
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


def pick_asset(assets, os_release=None, system=None, machine=None):
    system = system or osinfo.system_label()
    machine = machine or osinfo.machine()
    names = [(a.get("name", ""), a.get("browser_download_url", "")) for a in assets]

    def first(predicate):
        for name, url in names:
            if url and predicate(name.lower()):
                return name, url
        return None

    if system == "Windows":
        return first(lambda n: n.endswith(".exe") and "setup" in n) or first(lambda n: n.endswith(".zip") and "windows" in n)
    if system == "macOS":
        arch = "arm64" if machine == "arm64" else "x86_64"
        return (first(lambda n: n.endswith(".dmg") and arch in n) or first(lambda n: n.endswith(".dmg"))
                or first(lambda n: n.endswith(".zip") and "macos" in n))
    if os_release is None:
        try:
            with open("/etc/os-release", encoding="utf-8") as handle:
                os_release = handle.read().lower()
        except OSError:
            os_release = ""
    if re.search(r"debian|ubuntu|mint|pop|elementary|kali", os_release):
        order = (".deb", ".appimage", ".tar.gz")
    elif re.search(r"fedora|rhel|centos|rocky|alma|suse|mageia", os_release):
        order = (".rpm", ".appimage", ".tar.gz")
    else:
        order = (".appimage", ".tar.gz", ".deb", ".rpm")
    for extension in order:
        found = first(lambda n, e=extension: n.endswith(e))
        if found:
            return found
    return None


def parse_release(data):
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name") or ""
    if not parse_version(tag):
        return None
    asset = pick_asset(data.get("assets") or [])
    asset_name = asset[0] if asset else None
    asset_info = next((item for item in data.get("assets") or [] if item.get("name") == asset_name), {})
    return {
        "version": tag.lstrip("vV"),
        "tag": tag,
        "name": data.get("name") or tag,
        "notes": (data.get("body") or "").strip(),
        "url": data.get("html_url") or RELEASES_URL,
        "asset": asset,
        "digest": asset_info.get("digest") or "",
        "checksums": next((item.get("browser_download_url", "") for item in data.get("assets") or []
                           if item.get("name") == "SHA256SUMS"), ""),
    }


def fetch_latest():
    response = requests.get(API_LATEST, headers=HEADERS, timeout=8)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return parse_release(response.json())


def download_asset(release, progress=None):
    asset = release.get("asset")
    if not asset:
        raise RuntimeError("No compatible installer was found for this system.")
    name, url = asset
    filename = Path(name).name
    if not filename or filename != name or filename in (".", ".."):
        raise RuntimeError("The release contains an invalid installer filename.")

    cache = osinfo.cache_dir() / "updates"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / filename
    fd, temporary = tempfile.mkstemp(prefix=f".{filename}.", suffix=".part", dir=cache)
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as output, requests.get(url, headers=HEADERS, timeout=(10, 60),
                                                         stream=True) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0) or 0)
            received = 0
            for chunk in response.iter_content(chunk_size=128 * 1024):
                if not chunk:
                    continue
                output.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if progress:
                    progress(received, total)
            output.flush()
        expected = str(release.get("digest", "")).strip()
        if expected.startswith("sha256:"):
            expected = expected.split(":", 1)[1]
        if not expected and release.get("checksums"):
            checksum_response = requests.get(release["checksums"], headers=HEADERS, timeout=(10, 30))
            checksum_response.raise_for_status()
            for line in checksum_response.text.splitlines():
                match = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
                if match and Path(match.group(2)).name == filename:
                    expected = match.group(1).lower()
                    break
        if expected and digest.hexdigest().lower() != expected.lower():
            raise RuntimeError("The downloaded installer failed its SHA-256 integrity check.")
        Path(temporary).replace(target)
        if target.suffix.lower() == ".appimage":
            target.chmod(target.stat().st_mode | 0o111)
        return target
    except Exception:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def launch_installer(path):
    path = Path(path).resolve()
    suffix = path.suffix.lower()
    if osinfo.IS_WINDOWS:
        if suffix == ".exe":
            subprocess.Popen([str(path)], **osinfo.detached_kwargs())
            return "installer"
    if osinfo.IS_MAC:
        if suffix == ".dmg":
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise RuntimeError("Could not open the downloaded disk image.")
            return "installer"
    if suffix in (".deb", ".rpm"):
        package_manager = {
            "debian": "apt",
            "fedora": "dnf",
            "suse": "zypper",
        }.get(osinfo.linux_family())
        if suffix == ".deb":
            package_manager = "apt"
        elif package_manager not in ("dnf", "zypper"):
            package_manager = "dnf"
        install_args = (["install", "-y", str(path)] if package_manager != "zypper"
                        else ["--non-interactive", "install", str(path)])
        pkexec = shutil.which("pkexec")
        command = shutil.which(package_manager) if package_manager else None
        if pkexec and command:
            subprocess.Popen([pkexec, command, *install_args], **osinfo.detached_kwargs())
            return "installer"
    if suffix == ".appimage":
        subprocess.Popen([str(path)], **osinfo.detached_kwargs())
        return "installer"
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
        raise RuntimeError("Could not open the downloaded update file.")
    return "file"


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

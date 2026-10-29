import shutil
import subprocess

from .. import osinfo
from ..i18n import tr

REQUIRED = {
    "idevice_id": "libimobiledevice-utils",
    "ideviceinfo": "libimobiledevice-utils",
    "idevicebackup2": "libimobiledevice-utils",
    "idevicediagnostics": "libimobiledevice-utils",
    "idevicesyslog": "libimobiledevice-utils",
    "idevicepair": "libimobiledevice-utils",
    "ideviceenterrecovery": "libimobiledevice-utils",
    "idevicerestore": "idevicerestore",
    "ideviceinstaller": "ideviceinstaller",
    "irecovery": "libirecovery-utils",
}

LINUX_HINTS = {
    "debian": "sudo apt install libimobiledevice-utils ideviceinstaller idevicerestore usbmuxd libirecovery-utils",
    "arch": "sudo pacman -S libimobiledevice usbmuxd ideviceinstaller idevicerestore",
    "suse": "sudo zypper install libimobiledevice-tools ideviceinstaller idevicerestore usbmuxd",
    "fedora": "sudo dnf install libimobiledevice libimobiledevice-utils idevicerestore ideviceinstaller usbmuxd "
              "libirecovery-utils",
}


def install_hint():
    if osinfo.IS_MAC:
        return "brew install libimobiledevice ideviceinstaller idevicerestore libirecovery"
    if osinfo.IS_WINDOWS:
        return tr("Instala Apple Devices o iTunes y las herramientas libimobiledevice para Windows (mira el README).",
                  "Install Apple Devices or iTunes and the libimobiledevice tools for Windows (see the README).")
    return LINUX_HINTS.get(osinfo.linux_family(), LINUX_HINTS["fedora"])


class ToolMissing(Exception):
    def __init__(self, tool):
        super().__init__(tr(f"Falta '{tool}'. Instala los paquetes (mira el README).",
                            f"'{tool}' is missing. Install the packages (see the README)."))
        self.tool = tool


def missing_tools():
    return sorted(t for t in REQUIRED if not shutil.which(t))


def run(args, timeout=20):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, **osinfo.hidden_console_kwargs())
    except FileNotFoundError:
        raise ToolMissing(args[0])
    except subprocess.TimeoutExpired:
        return 124, b"", b"timeout"
    return p.returncode, p.stdout, p.stderr

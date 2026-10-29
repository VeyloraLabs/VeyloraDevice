import shutil
import subprocess

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

INSTALL_HINT = (
    "sudo dnf install libimobiledevice libimobiledevice-utils idevicerestore "
    "ideviceinstaller usbmuxd libirecovery-utils"
)


class ToolMissing(Exception):
    def __init__(self, tool):
        super().__init__(tr(f"Falta '{tool}'. Instala los paquetes (mira el README).",
                            f"'{tool}' is missing. Install the packages (see the README)."))
        self.tool = tool


def missing_tools():
    return sorted(t for t in REQUIRED if not shutil.which(t))


def run(args, timeout=20):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise ToolMissing(args[0])
    except subprocess.TimeoutExpired:
        return 124, b"", b"timeout"
    return p.returncode, p.stdout, p.stderr

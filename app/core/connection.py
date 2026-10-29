import glob
import os
import re

from .. import osinfo
from ..i18n import tr
from .tools import run

APPLE_VENDOR = "05ac"
BLOCK_FILE = "/etc/modprobe.d/ipheth-block.conf"


def apple_usb_present():
    if not osinfo.IS_LINUX:
        return False
    for vend in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        try:
            with open(vend) as f:
                if f.read().strip().lower() != APPLE_VENDOR:
                    continue
            with open(os.path.join(os.path.dirname(vend), "idProduct")) as f:
                if f.read().strip().lower().startswith("12"):
                    return True
        except OSError:
            pass
    return False


def ipheth_loaded():
    return os.path.isdir("/sys/module/ipheth")


def ipheth_blocked():
    return os.path.exists(BLOCK_FILE)


def _text(out, err):
    return (out + err).decode(errors="replace").strip()


def classify(text):
    low = (text or "").lower()
    codes = set(re.findall(r"(?<![\w.])(-\d{1,2})(?!\d)", text or ""))
    if "invalid hostid" in low or "-21" in codes:
        return "hostid"
    if "-8" in codes:
        return "mux"
    if "-5" in codes or "ssl" in low:
        return "ssl"
    if "passcode" in low:
        return "passcode"
    return None


def pair_status(udid):
    rc, out, err = run(["idevicepair", "-u", udid, "validate"], timeout=12)
    txt = _text(out, err)
    low = txt.lower()
    if rc == 0 and "success" in low:
        return "paired", txt
    if "passcode is set" in low:
        return "passcode", txt
    if "trust dialog" in low:
        return "pending", txt
    if "not paired" in low:
        return "unpaired", txt
    return (classify(txt) or "error"), txt


def request_pair(udid):
    rc, out, err = run(["idevicepair", "-u", udid, "pair"], timeout=20)
    txt = _text(out, err)
    low = txt.lower()
    if rc == 0 and "success" in low:
        return "paired"
    if "denied" in low:
        return "denied"
    if "trust dialog" in low:
        return "pending"
    if "passcode" in low:
        return "passcode"
    return classify(txt) or "error"


FIX_SCRIPTS = {
    "ipheth_once": "modprobe -r ipheth; systemctl restart usbmuxd",
    "ipheth_block": ('echo "install ipheth /bin/false" > /etc/modprobe.d/ipheth-block.conf; '
                     "modprobe -r ipheth; systemctl restart usbmuxd"),
    "ipheth_unblock": "rm -f /etc/modprobe.d/ipheth-block.conf",
    "reset_pairing": "systemctl stop usbmuxd; rm -f /var/lib/lockdown/*.plist; systemctl start usbmuxd",
    "start_usbmuxd": "systemctl restart usbmuxd",
}


class FixUnavailable(Exception):
    pass


def _mac_admin(script):
    return ["osascript", "-e", f'do shell script "{script}" with administrator privileges']


def _windows_admin(script):
    inner = script.replace("'", "''")
    return ["powershell", "-NoProfile", "-Command",
            f"Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList '-NoProfile','-Command','{inner}'"]


def fix_cmd(name):
    if osinfo.IS_LINUX:
        return ["pkexec", "sh", "-c", FIX_SCRIPTS[name]]
    if osinfo.IS_MAC and name == "reset_pairing":
        return _mac_admin("rm -f /var/db/lockdown/*.plist")
    if osinfo.IS_WINDOWS and name == "reset_pairing":
        return _windows_admin("Remove-Item \"$env:ProgramData\\Apple\\Lockdown\\*.plist\" -Force -ErrorAction SilentlyContinue")
    if osinfo.IS_WINDOWS and name == "start_usbmuxd":
        return _windows_admin("Restart-Service 'Apple Mobile Device Service'")
    if osinfo.IS_MAC and name == "start_usbmuxd":
        raise FixUnavailable(tr("En macOS el servicio usbmuxd es del sistema: desconecta y vuelve a conectar el cable o reinicia el Mac.",
                                "On macOS the usbmuxd service belongs to the system: unplug and replug the cable or restart the Mac."))
    raise FixUnavailable(tr("Esta reparación solo existe en Linux.", "This fix only exists on Linux."))

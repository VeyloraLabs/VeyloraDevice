import plistlib
import re

from ..i18n import tr
from . import connection
from .tools import ToolMissing, run


class DeviceError(Exception):
    pass


EXTRA_DOMAINS = ("com.apple.mobile.battery", "com.apple.disk_usage")


def list_udids():
    rc, out, err = run(["idevice_id", "-l"], timeout=10)
    lines = [l.strip() for l in out.decode(errors="replace").splitlines()]
    udids = [l for l in lines if re.fullmatch(r"[0-9A-Fa-f-]{20,}", l)]
    return udids, (out + err).decode(errors="replace").strip(), rc


def get_info(udid=None, domain=None):
    args = ["ideviceinfo", "-x"]
    if udid:
        args += ["-u", udid]
    if domain:
        args += ["-q", domain]
    rc, out, err = run(args, timeout=15)
    if rc != 0 or not out.strip():
        msg = (err or out).decode(errors="replace").strip() or tr("No se pudo leer el dispositivo", "Could not read the device")
        raise DeviceError(msg)
    return plistlib.loads(out)


def get_extra(udid):
    extra = {}
    for dom in EXTRA_DOMAINS:
        try:
            extra.update(get_info(udid, dom))
        except Exception:
            pass
    return extra


def get_full(udid):
    return get_info(udid), get_extra(udid)


def recovery_info():
    rc, out, _ = run(["irecovery", "-q"], timeout=8)
    if rc != 0:
        return None
    d = {}
    for line in out.decode(errors="replace").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            d[k.strip()] = v.strip()
    return d or None


_INSTALLER_STYLE = None


def installer_style():
    global _INSTALLER_STYLE
    if _INSTALLER_STYLE is None:
        rc, out, err = run(["ideviceinstaller", "--help"], timeout=10)
        txt = (out + err).decode(errors="replace")
        _INSTALLER_STYLE = "new" if ("COMMANDS" in txt and "uninstall BUNDLEID" in txt) else "old"
    return _INSTALLER_STYLE


def installer_cmd(action, udid=None, arg=None):
    new = installer_style() == "new"
    args = ["ideviceinstaller"] + (["-u", udid] if udid else [])
    if action == "list":
        return args + (["list", "--all", "--xml"] if new else ["-l", "-o", "list_all", "-o", "xml"])
    if action == "list_text":
        return args + (["list", "--all"] if new else ["-l", "-o", "list_all"])
    if action == "install":
        return args + (["install", arg] if new else ["-i", arg])
    if action == "uninstall":
        return args + (["uninstall", arg] if new else ["-U", arg])
    raise ValueError(action)


def list_apps(udid=None):
    rc, out, err = run(installer_cmd("list", udid), timeout=60)
    i = out.find(b"<?xml")
    if rc != 0 or i < 0:
        raise DeviceError((err or out).decode(errors="replace").strip() or tr("No se pudo listar las apps", "Could not list the apps"))
    data = plistlib.loads(out[i:])
    return data if isinstance(data, list) else data.get("Apps", [])


def uninstall_app(udid, bundle_id):
    rc, out, err = run(installer_cmd("uninstall", udid, bundle_id), timeout=120)
    txt = (out + err).decode(errors="replace").strip()
    low = txt.lower()
    if rc != 0 or "error" in low and "complete" not in low:
        raise DeviceError(txt or tr(f"código {rc}", f"code {rc}"))
    return txt


def poll(cache):
    try:
        udids, txt, rc = list_udids()
    except ToolMissing as e:
        return {"mode": "none", "error": str(e), "issue": "tools"}

    if udids:
        udid = udids[0]
        base = {"mode": "normal", "udid": udid, "count": len(udids), "info": None, "extra": {}}
        if udid in cache:
            info, extra = cache[udid]
            return dict(base, info=info, extra=extra)
        status, msg = connection.pair_status(udid)
        if status != "paired":
            return dict(base, issue=status, error=msg)
        try:
            info = get_info(udid)
        except DeviceError as e:
            return dict(base, issue=connection.classify(str(e)) or "error", error=str(e))
        extra = get_extra(udid)
        cache[udid] = (info, extra)
        return dict(base, info=info, extra=extra)

    try:
        rec = recovery_info()
    except ToolMissing:
        rec = None
    if rec:
        return {"mode": "recovery", "recovery": rec, "product": rec.get("PRODUCT", "")}

    if rc != 0 and "retrieve" in txt.lower():
        return {"mode": "none", "issue": "usbmuxd_down", "error": txt}
    if connection.apple_usb_present():
        return {"mode": "none", "issue": "mux", "ipheth": connection.ipheth_loaded()}
    return {"mode": "none", "issue": "no_usb"}

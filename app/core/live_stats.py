import plistlib

from . import device
from .tools import run


def find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = find_key(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_key(value, key)
            if found is not None:
                return found
    return None


def normalize_temperature(raw):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value > 200:
        value /= 100
    return value if -20 <= value <= 120 else None


def parse_ioreg_battery(output):
    result = {"temperature": None, "cycles": None, "health": None}
    start = output.find(b"<?xml")
    if start < 0:
        return result
    try:
        data = plistlib.loads(output[start:])
    except Exception:
        return result
    temperature = find_key(data, "Temperature")
    if temperature is None:
        temperature = find_key(data, "VirtualTemperature")
    result["temperature"] = normalize_temperature(temperature)
    cycles = find_key(data, "CycleCount")
    result["cycles"] = int(cycles) if isinstance(cycles, (int, float)) else None
    design = find_key(data, "DesignCapacity")
    full = find_key(data, "NominalChargeCapacity")
    if full is None:
        full = find_key(data, "AppleRawMaxCapacity")
    if isinstance(design, (int, float)) and isinstance(full, (int, float)) and design > 0:
        result["health"] = min(100.0, full * 100 / design)
    return result


def live_stats(udid, include_disk=True):
    stats = {"level": None, "charging": False, "full": False, "connected": False, "temperature": None,
             "cycles": None, "health": None, "disk": None}
    try:
        battery = device.get_info(udid, "com.apple.mobile.battery")
        level = battery.get("BatteryCurrentCapacity")
        stats["level"] = int(level) if isinstance(level, (int, float)) else None
        stats["charging"] = bool(battery.get("BatteryIsCharging"))
        stats["full"] = bool(battery.get("FullyCharged"))
        stats["connected"] = bool(battery.get("ExternalConnected"))
    except Exception:
        pass
    try:
        rc, out, _err = run(["idevicediagnostics", "-u", udid, "ioregentry", "AppleSmartBattery"], timeout=12)
        if rc == 0:
            stats.update(parse_ioreg_battery(out))
    except Exception:
        pass
    if include_disk:
        try:
            disk = device.get_info(udid, "com.apple.disk_usage")
            total = disk.get("TotalDataCapacity") or disk.get("TotalDiskCapacity")
            free = disk.get("TotalDataAvailable", disk.get("AmountDataAvailable"))
            if isinstance(total, (int, float)) and isinstance(free, (int, float)) and total > 0:
                stats["disk"] = (int(total), int(free))
        except Exception:
            pass
    return stats

def fmt_bytes(n, base=1000):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return str(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < base or unit == "TB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= base


def fmt_speed(bps):
    return fmt_bytes(bps) + "/s" if bps else ""

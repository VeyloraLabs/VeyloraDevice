import json
from pathlib import Path

import requests

API = "https://api.ipsw.me/v4"
HEADERS = {"User-Agent": "VeyloraDevice/0.1 (VeyloraLabs)"}
CACHE = Path.home() / ".cache" / "veylora"


def get_devices():
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / "devices.json"
    try:
        r = requests.get(f"{API}/devices", headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        f.write_text(json.dumps(data))
    except Exception:
        if not f.exists():
            raise
        data = json.loads(f.read_text())
    return sorted(data, key=lambda d: d.get("name", ""))


def get_firmwares(identifier):
    r = requests.get(f"{API}/device/{identifier}", params={"type": "ipsw"},
                     headers=HEADERS, timeout=20)
    r.raise_for_status()
    fws = r.json().get("firmwares", [])
    fws.sort(key=lambda f: f.get("releasedate") or f.get("uploaddate") or "", reverse=True)
    return fws

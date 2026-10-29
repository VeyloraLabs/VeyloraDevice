import csv
import io
import json
import re
import time
from pathlib import Path

import requests

from . import catalog

CSV_URL = "https://storage.googleapis.com/play_public/supported_devices.csv"
JSON_URL = "https://cdn.jsdelivr.net/gh/bsthen/device-models/devices.json"
WIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "VeyloraDevice/1.0 (VeyloraLabs; Linux desktop device manager)"}
CACHE = Path.home() / ".cache" / "veylora"
MAX_AGE = 30 * 24 * 3600

BRANDS = {"lge": "LG", "oneplus": "OnePlus", "htc": "HTC", "zte": "ZTE", "oppo": "OPPO", "tcl": "TCL", "poco": "POCO",
          "realme": "realme", "hmd global": "Nokia", "huawei": "Huawei", "honor": "Honor", "asus": "ASUS",
          "motorola": "Motorola", "google": "Google", "samsung": "Samsung", "xiaomi": "Xiaomi", "sony": "Sony"}
_memory = {}


def parse_supported_csv(data):
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16", errors="replace")
    else:
        text = data.decode("utf-8-sig", errors="replace")
    devices = []
    for index, row in enumerate(csv.reader(io.StringIO(text))):
        if index == 0 or len(row) < 4:
            continue
        brand, name, device, model = (cell.strip() for cell in row[:4])
        if name or model:
            devices.append([brand, name, device, model])
    return devices


def parse_mirror_json(data):
    devices = []
    if isinstance(data, dict):
        for code, entry in data.items():
            if isinstance(entry, dict):
                devices.append([entry.get("brand", ""), entry.get("name", ""), str(code), str(code)])
    elif isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                devices.append([entry.get("brand", ""), entry.get("name", ""),
                                entry.get("device", "") or entry.get("code", ""),
                                entry.get("model", "") or entry.get("code", "")])
    return [d for d in devices if d[1]]


def _download_devices():
    try:
        response = requests.get(CSV_URL, headers=HEADERS, timeout=25)
        response.raise_for_status()
        devices = parse_supported_csv(response.content)
        if devices:
            return devices
    except Exception:
        pass
    response = requests.get(JSON_URL, headers=HEADERS, timeout=25)
    response.raise_for_status()
    return parse_mirror_json(response.json())


def load_devices():
    cache = CACHE / "android_devices.json"
    stale = None
    try:
        stale = json.loads(cache.read_text())
        if time.time() - cache.stat().st_mtime < MAX_AGE:
            return stale
    except (OSError, ValueError):
        pass
    try:
        devices = _download_devices()
        CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(devices))
        return devices
    except Exception:
        return stale or []


def find_device(props, devices):
    model = (props.get("ro.product.model") or "").strip().lower()
    code = (props.get("ro.product.device") or "").strip().lower()
    name = (props.get("ro.product.name") or "").strip().lower()
    both = single_model = single_code = None
    for brand, marketing, device, dev_model in devices:
        d, m = device.lower(), dev_model.lower()
        if model and code and m == model and d == code:
            both = both or (brand, marketing)
        elif model and m == model:
            single_model = single_model or (brand, marketing)
        elif (code and d == code) or (name and d == name):
            single_code = single_code or (brand, marketing)
    return both or single_model or single_code


def pretty_brand(brand):
    brand = (brand or "").strip()
    return BRANDS.get(brand.lower(), brand if not brand.islower() else brand.title())


def display_name(props, found):
    if found:
        brand, marketing = pretty_brand(found[0]), found[1]
        if brand and not marketing.lower().startswith(brand.lower()):
            return f"{brand} {marketing}".strip()
        return marketing
    maker = pretty_brand(props.get("ro.product.manufacturer") or props.get("ro.product.brand") or "")
    model = (props.get("ro.product.model") or "").strip()
    if maker and model and not model.lower().startswith(maker.lower()):
        return f"{maker} {model}"
    return model or maker


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def pick_wiki_page(pages, marketing, brand):
    wanted = _tokens(marketing)
    ignore = _tokens(brand)
    best, best_key = None, None
    for page in pages:
        thumb = (page.get("thumbnail") or {}).get("source")
        if not thumb:
            continue
        title = _tokens(page.get("title", "")) - ignore
        if not title or not title <= wanted:
            continue
        ratio = len(wanted & title) / max(1, len(wanted - ignore))
        if ratio < 0.6:
            continue
        key = (ratio, len(title))
        if best_key is None or key > best_key:
            best, best_key = thumb, key
    return best


def wiki_image_url(marketing, brand):
    params = {"action": "query", "format": "json", "generator": "search", "gsrlimit": 8,
              "gsrsearch": f"{brand} {marketing} smartphone".strip(), "prop": "pageimages", "piprop": "thumbnail",
              "pithumbsize": 700, "redirects": 1}
    response = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=20)
    response.raise_for_status()
    pages = list((response.json().get("query") or {}).get("pages", {}).values())
    return pick_wiki_page(pages, marketing, brand)


def identify(props):
    key = f"{props.get('ro.product.model', '')}|{props.get('ro.product.device', '')}"
    if key in _memory:
        return _memory[key]
    found = find_device(props, load_devices())
    result = {"name": display_name(props, found), "image": None}
    if found:
        url = wiki_image_url(found[1], pretty_brand(found[0]))
        if url:
            result["image"] = catalog.download_image(url)
    _memory[key] = result
    return result

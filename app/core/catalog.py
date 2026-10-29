import hashlib
import json
import re
from collections import OrderedDict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

SITE = "https://ipsw.me/"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) VeyloraDevice/0.2"}
CACHE = Path.home() / ".cache" / "veylora"

FALLBACK_CATEGORIES = [("iPhone", "iPhone"), ("iPad", "iPad"), ("Mac", "Mac"), ("Vision", "Vision Pro"),
                       ("AppleTV", "Apple TV"), ("AudioAccessory", "HomePod"), ("iPod", "iPod touch"),
                       ("Watch", "Apple Watch")]

RE_PRODUCT = re.compile(r"^/product/([^/]+)/?$")
RE_DEVICE = re.compile(r"^/([A-Za-z][A-Za-z0-9]*\d,\d+)/?$")
PREFIX_TO_CATEGORY = {"iPhone": "iPhone", "iPad": "iPad", "iPod": "iPod", "Watch": "Watch",
                      "AppleTV": "AppleTV", "AudioAccessory": "AudioAccessory", "RealityDevice": "Vision"}


def _img_url(attrs):
    for k in ("src", "data-src", "data-lazy-src", "data-original", "srcset", "data-srcset"):
        v = attrs.get(k)
        if v:
            first = v.split(",")[0].strip().split(" ")[0]
            if first and not first.startswith("data:"):
                return first
    style = attrs.get("style") or ""
    m = re.search(r"url\(['\"]?([^'\")]+)", style)
    if m and not m.group(1).startswith("data:"):
        return m.group(1)
    return None


class _Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events = []
        self._a = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a":
            self._a = {"href": a.get("href", ""), "text": [], "imgs": [], "alt": ""}
            return
        if tag in ("img", "source"):
            url, alt = _img_url(a), a.get("alt", "")
            if url:
                if self._a is not None:
                    self._a["imgs"].append(url)
                    self._a["alt"] = self._a["alt"] or alt
                else:
                    self.events.append(("img", url, alt))
            elif self._a is not None and alt:
                self._a["alt"] = self._a["alt"] or alt
        elif self._a is not None and a.get("style"):
            u = _img_url({"style": a["style"]})
            if u:
                self._a["imgs"].append(u)

    def handle_data(self, data):
        if self._a is not None and data.strip():
            self._a["text"].append(" ".join(data.split()))

    def handle_endtag(self, tag):
        if tag == "a" and self._a is not None:
            self.events.append(("a", self._a))
            self._a = None


def _clean_name(parts, alt=""):
    name = " ".join(parts).strip() or (alt or "").strip()
    words = name.split()
    n = len(words)
    if n >= 2 and n % 2 == 0 and words[: n // 2] == words[n // 2:]:
        name = " ".join(words[: n // 2])
    return name


def parse_anchors(html, base=SITE):
    p = _Scan()
    p.feed(html)
    res = OrderedDict()
    ev = p.events
    for i, e in enumerate(ev):
        if e[0] != "a":
            continue
        a = e[1]
        href = a["href"]
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        full = urljoin(base, href)
        if urlparse(full).netloc not in ("", urlparse(base).netloc):
            continue
        path = urlparse(full).path
        img = a["imgs"][0] if a["imgs"] else None
        if not img and i > 0 and ev[i - 1][0] == "img":
            img = ev[i - 1][1]
        if not img and i + 1 < len(ev) and ev[i + 1][0] == "img":
            img = ev[i + 1][1]
        name = _clean_name(a["text"], a["alt"])
        cur = res.setdefault(path, {"name": "", "img": None})
        cur["name"] = cur["name"] or name
        if img and not cur["img"]:
            cur["img"] = urljoin(base, img)
    return res


def _get(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def load_cache(name):
    try:
        return json.loads((CACHE / f"{name}.json").read_text())
    except Exception:
        return None


def save_cache(name, data):
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / f"{name}.json").write_text(json.dumps(data))
    except OSError:
        pass


def _debug_dump(name, html):
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / f"debug_{name}.html").write_text(html)
    except OSError:
        pass


def fetch_home():
    html = _get(SITE)
    anchors = parse_anchors(html)
    cats, latest = [], []
    for path, d in anchors.items():
        m = RE_PRODUCT.match(path)
        if m:
            cats.append({"code": m.group(1), "name": d["name"] or m.group(1), "img": d["img"]})
            continue
        m = RE_DEVICE.match(path)
        if m and len(latest) < 12:
            latest.append({"ident": m.group(1), "name": d["name"] or m.group(1), "img": d["img"]})
    if not cats:
        _debug_dump("home", html)
        cats = [{"code": c, "name": n, "img": None} for c, n in FALLBACK_CATEGORIES]
    data = {"categories": cats, "latest": latest}
    save_cache("home", data)
    return data


def category_of_identifier(ident):
    m = re.match(r"([A-Za-z]+)\d", ident or "")
    if not m:
        return None
    pre = m.group(1)
    if pre in PREFIX_TO_CATEGORY:
        return PREFIX_TO_CATEGORY[pre]
    return "Mac" if "mac" in pre.lower() else None


def fetch_category_devices(code, api_devices=()):
    html = _get(urljoin(SITE, f"product/{code}/"))
    anchors = parse_anchors(html)
    devs, seen = [], set()
    for path, d in anchors.items():
        m = RE_DEVICE.match(path)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            devs.append({"ident": m.group(1), "name": d["name"] or m.group(1), "img": d["img"]})
    if not devs:
        _debug_dump(f"product_{code}", html)
    for a in api_devices:
        ident = a.get("identifier", "")
        if ident not in seen and category_of_identifier(ident) == code:
            seen.add(ident)
            devs.append({"ident": ident, "name": a.get("name") or ident, "img": None})
    save_cache(f"devices_{code}", devs)
    return devs


def device_image_url(ident):
    code = category_of_identifier(ident)
    if not code:
        return None

    def find(devs):
        for d in devs or []:
            if d.get("ident") == ident and d.get("img"):
                return d["img"]
        return None

    url = find(load_cache(f"devices_{code}"))
    if url:
        return url
    return find(fetch_category_devices(code))


def download_image(url):
    d = CACHE / "img"
    d.mkdir(parents=True, exist_ok=True)
    ext = Path(urlparse(url).path).suffix or ".img"
    f = d / (hashlib.sha1(url.encode()).hexdigest() + ext)
    if f.exists() and f.stat().st_size > 0:
        return str(f)
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    f.write_bytes(r.content)
    return str(f)

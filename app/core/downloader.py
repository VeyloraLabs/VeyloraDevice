import hashlib
import os
import time

import requests

from ..i18n import tr


class Cancelled(Exception):
    pass


class DownloadJob:

    def __init__(self, url, dest, sha1=None, size=0):
        self.url, self.dest, self.sha1, self.size = url, dest, sha1, size
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self, on_progress, on_status):
        os.makedirs(os.path.dirname(self.dest), exist_ok=True)
        already = os.path.exists(self.dest) and (not self.size or os.path.getsize(self.dest) == self.size)
        if already:
            on_status(tr("Ya estaba descargado, verificando…", "Already downloaded, verifying…"))
        else:
            self._download(on_progress, on_status)
        self._verify(on_status)
        return self.dest

    def _download(self, on_progress, on_status):
        part = self.dest + ".part"
        pos = os.path.getsize(part) if os.path.exists(part) else 0
        headers = {"Range": f"bytes={pos}-"} if pos else {}
        on_status(tr("Reanudando descarga…", "Resuming download…") if pos else tr("Conectando…", "Connecting…"))
        with requests.get(self.url, headers=headers, stream=True, timeout=30) as r:
            if r.status_code == 416 and pos:
                os.replace(part, self.dest)
                return
            r.raise_for_status()
            if pos and r.status_code != 206:
                pos = 0
            total = pos + int(r.headers.get("Content-Length") or 0) or self.size
            done, base, t0, last = pos, pos, time.time(), 0.0
            on_status(tr("Descargando…", "Downloading…"))
            with open(part, "ab" if pos else "wb") as f:
                for chunk in r.iter_content(256 * 1024):
                    if self._cancel:
                        raise Cancelled()
                    f.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    if now - last > 0.2:
                        on_progress(done, total, (done - base) / max(now - t0, 1e-6))
                        last = now
        on_progress(done, total, 0)
        os.replace(part, self.dest)

    def _verify(self, on_status):
        if not self.sha1:
            return
        on_status(tr("Verificando SHA1…", "Verifying SHA1…"))
        h = hashlib.sha1()
        with open(self.dest, "rb") as f:
            while chunk := f.read(1 << 20):
                if self._cancel:
                    raise Cancelled()
                h.update(chunk)
        if h.hexdigest().lower() != self.sha1.lower():
            os.remove(self.dest)
            raise ValueError(tr("El SHA1 no coincide: archivo corrupto, lo he borrado. Vuelve a descargarlo.",
                                "SHA1 mismatch: the file is corrupt and was deleted. Download it again."))

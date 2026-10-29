from PySide6.QtCore import QObject, QTimer, Signal

from ..core import connection, device, tools
from ..dispatch import run_async

AUTO_REPAIR_ISSUES = ("mux", "ssl", "hostid", "error")


class DeviceMonitor(QObject):

    changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = {"mode": "none"}
        self._busy = False
        self._cache = {}
        self._asked = {}
        self._auto_fixed = False
        self._repairing = False
        self._last = object()
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self.poll)

    def start(self):
        self._timer.start()
        self.poll()

    def refresh(self):
        self._cache.clear()
        self._last = object()
        self.poll()

    def poll(self):
        if self._busy:
            return
        self._busy = True
        cache = self._cache
        run_async(lambda: device.poll(cache), self._done, self._fail)

    def request_pair(self, udid=None):
        udid = udid or self.state.get("udid")
        if not udid:
            return
        self._asked[udid] = "pending"
        run_async(lambda: connection.request_pair(udid), lambda st: self._pair_done(udid, st),
                  lambda e: self._pair_done(udid, "error"))

    def _pair_done(self, udid, status):
        if status == "paired":
            self._asked.pop(udid, None)
        else:
            self._asked[udid] = "denied" if status == "denied" else "pending"
        self._last = object()
        self.poll()

    def _auto_repair(self):
        self._auto_fixed = True
        self._repairing = True

        def finish():
            self._repairing = False
            self._cache.clear()
            self._last = object()
            self.poll()

        run_async(lambda: tools.run(connection.fix_cmd("reset_pairing"), timeout=120),
                  lambda _res: finish(), lambda _e: finish())

    def _done(self, state):
        self._busy = False
        issue = state.get("issue")
        if issue == "no_usb" or state["mode"] == "recovery" or (state["mode"] == "normal" and not issue):
            self._auto_fixed = False
        if self._repairing:
            state = dict(state, issue="repairing")
        elif issue in AUTO_REPAIR_ISSUES and not self._auto_fixed and (state["mode"] == "normal" or issue == "mux"):
            self._auto_repair()
            state = dict(state, issue="repairing")
        if state["mode"] != "normal":
            self._asked.clear()
        elif state.get("issue") in ("unpaired", "pending"):
            udid = state["udid"]
            asked = self._asked.get(udid)
            if asked is None:
                self.request_pair(udid)
            state = dict(state, issue="denied" if asked == "denied" else "pending")
        key = (state["mode"], state.get("udid"), (state.get("recovery") or {}).get("ECID"),
               state.get("issue"), bool(state.get("info")))
        if key != self._last:
            self._last = key
            self.state = state
            self.changed.emit(state)

    def _fail(self, exc):
        self._busy = False
        self._done({"mode": "none", "error": str(exc), "issue": "error"})

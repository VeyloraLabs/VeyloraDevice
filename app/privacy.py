import re
import time

from PySide6.QtCore import QObject, QSettings, QTimer, Signal

from .i18n import tr

CLICKS_TO_REVEAL = 5
REVEAL_SECONDS = 5
CLICK_WINDOW = 3.0
MASK = "••••••••••"

_SENSITIVE = re.compile(
    r"serie|serial|imei|meid|udid|ecid|iccid|imsi|\bmac\b|die id|tel[eé]fono|phone number|"
    r"nombre del dispositivo|device name|wi-?fi ip|ip de wi-?fi|direcci[oó]n|address", re.IGNORECASE)


class _Bus(QObject):
    changed = Signal()


bus = _Bus()


def enabled():
    return str(QSettings().value("hide_sensitive", "false")).lower() in ("true", "1")


def set_enabled(value):
    QSettings().setValue("hide_sensitive", bool(value))
    bus.changed.emit()


def is_sensitive(label):
    return bool(_SENSITIVE.search(str(label)))


def hidden_text():
    return tr("(oculto)", "(hidden)")


def generic_name(name, fallback):
    return fallback if enabled() and name else name


def report_value(label, value):
    return hidden_text() if enabled() and is_sensitive(label) else value


def searchable(label, value):
    if enabled() and is_sensitive(label):
        return str(label)
    return f"{label} {value}"


def hint():
    return tr(f"Contenido oculto. Haz {CLICKS_TO_REVEAL} clics para verlo {REVEAL_SECONDS} segundos.",
              f"Hidden content. Click {CLICKS_TO_REVEAL} times to see it for {REVEAL_SECONDS} seconds.")


class Reveal:
    def __init__(self):
        self._clicks = {}
        self._last = {}
        self._until = {}

    def shown(self, key):
        return not enabled() or not is_sensitive(key) or time.monotonic() < self._until.get(key, 0)

    def display(self, key, value):
        if self.shown(key):
            return str(value), False
        count = self._clicks.get(key, 0)
        recent = time.monotonic() - self._last.get(key, 0) <= CLICK_WINDOW
        suffix = f"   {count}/{CLICKS_TO_REVEAL}" if count and recent else ""
        return MASK + suffix, True

    def click(self, key, refresh):
        if self.shown(key):
            return True
        now = time.monotonic()
        count = self._clicks.get(key, 0) + 1 if now - self._last.get(key, 0) <= CLICK_WINDOW else 1
        self._last[key] = now
        if count >= CLICKS_TO_REVEAL:
            self._clicks[key] = 0
            self._until[key] = now + REVEAL_SECONDS
            QTimer.singleShot(int(REVEAL_SECONDS * 1000) + 60, refresh)
        else:
            self._clicks[key] = count
            QTimer.singleShot(int(CLICK_WINDOW * 1000) + 60, refresh)
        refresh()
        return self.shown(key)

    def reset(self):
        self._clicks.clear()
        self._last.clear()
        self._until.clear()


def fill_table(table, rows, reveal):
    from PySide6.QtWidgets import QTableWidgetItem
    table.setRowCount(len(rows))
    for index, (label, value) in enumerate(rows):
        text, hidden = reveal.display(label, value)
        item = QTableWidgetItem(text)
        item.setToolTip(hint() if hidden else str(value))
        table.setItem(index, 0, QTableWidgetItem(str(label)))
        table.setItem(index, 1, item)


def connect_clicks(table, get_rows, reveal, refresh):
    def clicked(row, column):
        rows = get_rows()
        if column == 1 and 0 <= row < len(rows) and enabled() and is_sensitive(rows[row][0]):
            reveal.click(rows[row][0], refresh)

    table.cellClicked.connect(clicked)


def clean_for_copy(label, value):
    return None if enabled() and is_sensitive(label) else value

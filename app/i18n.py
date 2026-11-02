import weakref

from PySide6.QtCore import QObject, QSettings, Signal


class _Bus(QObject):
    changing = Signal(str)
    changed = Signal(str)


_bus = _Bus()
_bindings = []


def lang():
    return "es" if str(QSettings().value("language", "en")) == "es" else "en"


def tr(es, en):
    return text(es, en)


def text(es, en, language=None):
    return es if (language or lang()) == "es" else en


def set_lang(code):
    code = "es" if code == "es" else "en"
    if code == lang():
        return
    _bus.changing.emit(code)
    QSettings().setValue("language", code)
    for ref, method, es, en in list(_bindings):
        w = ref()
        if w is not None:
            getattr(w, method)(tr(es, en))
    _bus.changed.emit(code)


def bind(widget, method, es, en):
    getattr(widget, method)(tr(es, en))
    _bindings.append((weakref.ref(widget), method, es, en))
    return widget


def on_change(callback):
    _bus.changed.connect(callback)


def on_change_start(callback):
    _bus.changing.connect(callback)

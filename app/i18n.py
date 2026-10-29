import weakref

from PySide6.QtCore import QObject, QSettings, Signal


class _Bus(QObject):
    changed = Signal(str)


_bus = _Bus()
_bindings = []


def lang():
    return "es" if str(QSettings().value("language", "en")) == "es" else "en"


def tr(es, en):
    return es if lang() == "es" else en


def set_lang(code):
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

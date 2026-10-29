import threading
import traceback

from PySide6.QtCore import QObject, Signal, Slot


class _Dispatcher(QObject):
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._invoke)

    @Slot(object)
    def _invoke(self, fn):
        try:
            fn()
        except Exception:
            traceback.print_exc()


_disp = None


def init():
    global _disp
    _disp = _Dispatcher()


def post(fn):
    _disp.call.emit(fn)


def run_async(fn, on_done=None, on_error=None):

    def target():
        try:
            res = fn()
        except Exception as e:
            if on_error:
                post(lambda e=e: on_error(e))
            else:
                traceback.print_exc()
            return
        if on_done:
            post(lambda: on_done(res))

    threading.Thread(target=target, daemon=True).start()

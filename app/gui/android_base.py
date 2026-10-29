from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, ComboBox, FluentIcon as FIF,
                            IndeterminateProgressBar, MessageBox, MessageBoxBase, SubtitleLabel)

from .. import i18n, privacy, theme
from ..core import android
from ..dispatch import run_async
from ..i18n import tr
from .components import Banner, Page, Pill, toast
from .icons import android_icon

DANGER_BUTTON = (f"PrimaryPushButton {{ background:{theme.DANGER}; border:1px solid {theme.DANGER}; color:white; }}"
                 f"PrimaryPushButton:hover {{ background:#f0565b; border-color:#f0565b; }}"
                 f"PrimaryPushButton:pressed {{ background:#c93a3f; border-color:#c93a3f; }}")

STATUS_INFO = {
    "device": ("Conectado", "Connected", "ok"),
    "fastboot": ("Modo Fastboot", "Fastboot mode", "ok"),
    "unauthorized": ("Sin autorizar", "Unauthorized", "warn"),
    "offline": ("Sin conexión", "Offline", "warn"),
    "no permissions": ("Sin permiso", "No permission", "err"),
}


def status_info(status):
    es, en, kind = STATUS_INFO.get(status, (status or "—", status or "—", "muted"))
    return tr(es, en), kind


class AndroidMonitor(QObject):

    changed = Signal(dict)
    selection_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._last = None
        self.state = {"available": True, "devices": [], "error": ""}
        self.selected = None
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self.poll)

    @property
    def devices(self):
        return self.state["devices"]

    def current(self):
        return next((d for d in self.devices if d["serial"] == self.selected), None)

    def start(self):
        self._timer.start()
        self.poll()

    def refresh(self):
        self._last = None
        self.poll()

    def select(self, serial):
        if serial != self.selected and any(d["serial"] == serial for d in self.devices):
            self.selected = serial
            self.selection_changed.emit(serial)
            self.changed.emit(self.state)

    def restart_server(self, on_done=None, on_error=None):
        def done(_result):
            self.refresh()
            if on_done:
                on_done()

        run_async(android.restart_server, done, on_error)

    def poll(self):
        if self._busy:
            return
        self._busy = True
        run_async(android.poll, self._done, self._fail)

    def _done(self, state):
        self._busy = False
        key = (state["available"], state["error"], tuple(
            (d["serial"], d["status"], d["model"], d["product"], d["device"]) for d in state["devices"]))
        if key == self._last:
            return
        self._last = key
        self.state = state
        previous = self.selected
        serials = [d["serial"] for d in state["devices"]]
        if previous not in serials:
            ready = [d["serial"] for d in state["devices"] if d["status"] == "device"]
            self.selected = (ready or serials or [None])[0]
        if self.selected != previous:
            self.selection_changed.emit(self.selected)
        self.changed.emit(state)

    def _fail(self, error):
        self._busy = False
        self._done({"available": True, "devices": [], "error": str(error)})


def describe_state(state, device, fastboot_ok=False):
    if not state["available"]:
        return ("adb_missing", tr(
            "<b>ADB no está instalado.</b> Instala las herramientas de Android y pulsa Buscar de nuevo: "
            "<b>sudo dnf install android-tools</b> (Fedora) o <b>sudo apt install adb fastboot</b> (Debian/Ubuntu).",
            "<b>ADB is not installed.</b> Install the Android tools and press Search again: "
            "<b>sudo dnf install android-tools</b> (Fedora) or <b>sudo apt install adb fastboot</b> (Debian/Ubuntu)."))
    if state["error"] and not state["devices"]:
        return ("error", tr("<b>ADB dio un error:</b> ", "<b>ADB reported an error:</b> ") + state["error"])
    if not state["devices"] or device is None:
        return ("no_devices", tr(
            "<b>Conecta tu Android.</b> En el móvil: Ajustes → Acerca del teléfono → toca 7 veces «Número de "
            "compilación»; después Opciones de desarrollador → activa <b>Depuración USB</b>, conecta el cable y acepta "
            "el aviso «¿Permitir depuración USB?».",
            "<b>Connect your Android.</b> On the phone: Settings → About phone → tap “Build number” 7 times; then "
            "Developer options → turn on <b>USB debugging</b>, plug in the cable and accept the “Allow USB "
            "debugging?” prompt."))
    status = device["status"]
    if status == "unauthorized":
        return ("unauthorized", tr(
            "<b>Mira la pantalla del móvil y acepta «¿Permitir depuración USB?»</b> (desbloquéalo antes). Marca "
            "«Permitir siempre desde este equipo» para que no vuelva a preguntar.",
            "<b>Look at the phone screen and accept “Allow USB debugging?”</b> (unlock it first). Tick “Always allow "
            "from this computer” so it does not ask again."))
    if status == "no permissions":
        return ("no_permissions", tr(
            "<b>Linux no puede acceder al USB del móvil.</b> Desconecta y vuelve a conectar el cable. Si sigue igual, "
            "tu usuario no tiene permiso USB para este móvil: revisa las reglas udev de ADB de tu distribución.",
            "<b>Linux cannot access the phone's USB.</b> Unplug and replug the cable. If it stays the same, your user "
            "has no USB permission for this phone: check your distribution's ADB udev rules."))
    if status == "offline":
        return ("offline", tr(
            "<b>El móvil aparece sin conexión.</b> Reconecta el cable. Si sigue así, desactiva y vuelve a activar "
            "«Depuración USB» o reinicia el servidor ADB.",
            "<b>The phone shows as offline.</b> Replug the cable. If it persists, turn “USB debugging” off and on "
            "again or restart the ADB server."))
    if status == "fastboot":
        if fastboot_ok:
            return ("fastboot", "")
        return ("fastboot_only", tr(
            "<b>El móvil está en modo Fastboot.</b> Esta página necesita Android encendido con la depuración USB "
            "activa. Para salir de Fastboot usa Dispositivo → Salir de Fastboot.",
            "<b>The phone is in Fastboot mode.</b> This page needs Android running with USB debugging on. To leave "
            "Fastboot use Device → Leave Fastboot."))
    if status == "device":
        return ("ready", "")
    return ("other", tr(f"<b>Estado ADB: {status}.</b> Reconecta el dispositivo y pulsa Buscar de nuevo.",
                        f"<b>ADB state: {status}.</b> Reconnect the device and press Search again."))


BANNER_BUTTONS = {
    "adb_missing": (("Buscar de nuevo", "Search again"), None, FIF.DEVELOPER_TOOLS),
    "error": (("Reiniciar servidor ADB", "Restart ADB server"), None, FIF.INFO),
    "no_devices": (("Buscar de nuevo", "Search again"), ("Conectar por Wi-Fi…", "Connect over Wi-Fi…"), FIF.PHONE),
    "unauthorized": (("Buscar de nuevo", "Search again"), ("Reiniciar servidor ADB", "Restart ADB server"),
                     FIF.CERTIFICATE),
    "no_permissions": (("Buscar de nuevo", "Search again"), ("Reiniciar servidor ADB", "Restart ADB server"),
                       FIF.CONNECT),
    "offline": (("Reiniciar servidor ADB", "Restart ADB server"), ("Buscar de nuevo", "Search again"), FIF.SYNC),
    "fastboot_only": (None, None, FIF.DEVELOPER_TOOLS),
    "other": (("Buscar de nuevo", "Search again"), None, FIF.INFO),
}


class DeviceBar(QWidget):

    def __init__(self, monitor, parent=None):
        super().__init__(parent)
        self.monitor = monitor
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        self.card = CardWidget()
        self.card.setBorderRadius(12)
        row = QHBoxLayout(self.card)
        row.setContentsMargins(16, 8, 12, 8)
        row.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(android_icon().pixmap(22, 22))
        row.addWidget(logo)
        row.addWidget(i18n.bind(CaptionLabel(), "setText", "Varios dispositivos conectados", "Several devices connected"))
        self.combo = ComboBox()
        self.combo.setMinimumWidth(300)
        self.combo.currentIndexChanged.connect(self._picked)
        row.addWidget(self.combo, 1)
        self.pill = Pill("", "muted")
        row.addWidget(self.pill)
        outer.addWidget(self.card)
        self.progress = IndeterminateProgressBar(start=False)
        self.progress.setVisible(False)
        outer.addWidget(self.progress)

        monitor.changed.connect(lambda _state: self.rebuild())
        i18n.on_change(lambda _code: self.rebuild())
        privacy.bus.changed.connect(self.rebuild)
        self.rebuild()

    def rebuild(self):
        devices = self.monitor.devices
        self.combo.blockSignals(True)
        self.combo.clear()
        for item in devices:
            text, _kind = status_info(item["status"])
            suffix = "" if item["status"] == "device" else f"  ·  {text}"
            shown = privacy.MASK if privacy.enabled() else item["serial"]
            self.combo.addItem(f"{android.device_label(item)}  ·  {shown}{suffix}", userData=item["serial"])
        index = self.combo.findData(self.monitor.selected) if self.monitor.selected else -1
        self.combo.setCurrentIndex(index if index >= 0 else (0 if devices else -1))
        self.combo.blockSignals(False)
        device = self.monitor.current()
        if device:
            text, kind = status_info(device["status"])
            self.pill.setText(text)
            self.pill.set_kind(kind)
        self.card.setVisible(len(devices) > 1)

    def _picked(self, _index):
        serial = self.combo.currentData()
        if serial:
            self.monitor.select(serial)

    def set_busy(self, busy):
        self.progress.setVisible(busy)
        if busy:
            self.progress.start()
        else:
            self.progress.stop()
        self.combo.setEnabled(not busy)


class AndroidPage(Page):

    def __init__(self, name, title, subtitle, monitor, scroll=False, fastboot_ok=False, parent=None):
        super().__init__(name, title, subtitle, scroll=scroll, parent=parent)
        self.monitor = monitor
        self.fastboot_ok = fastboot_ok
        self._gen = 0
        self._tasks = 0
        self._ready_key = None
        self._loaded = False
        self._built = False
        self._banner_code = None

        self.banner = Banner()
        self.banner.btn1.clicked.connect(lambda: self._banner_action(1))
        self.banner.btn2.clicked.connect(lambda: self._banner_action(2))
        self.body.addWidget(self.banner)
        self.devbar = DeviceBar(monitor)
        self.body.addWidget(self.devbar)
        self.content_layout = self.body

        QShortcut(QKeySequence("F5"), self, activated=self.reload).setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut)
        monitor.changed.connect(lambda _state: self._sync())
        i18n.on_change(lambda _code: self._sync())

    def finish_setup(self):
        self._built = True
        self._sync()

    @property
    def serial(self):
        return self.monitor.selected

    @property
    def device(self):
        return self.monitor.current()

    @property
    def ready(self):
        device = self.device
        if not device:
            return False
        return device["status"] == "device" or (self.fastboot_ok and device["status"] == "fastboot")

    @property
    def busy(self):
        return self._tasks > 0

    def can_act(self):
        return self.ready and not self.busy

    def guard(self, callback):
        generation = self._gen

        def inner(*args):
            if generation == self._gen:
                callback(*args)

        return inner

    def load(self):
        pass

    def on_device_changed(self):
        pass

    def update_actions(self):
        pass

    def reload(self):
        self._gen += 1
        self._loaded = False
        self._sync()
        self.monitor.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_loaded()

    def _ensure_loaded(self):
        if self.ready and not self._loaded and self.isVisible():
            self._loaded = True
            self.load()

    def _sync(self):
        if not self._built:
            return
        device = self.device
        key = (self.serial, device["status"] if device else None)
        if key != self._ready_key:
            self._ready_key = key
            self._gen += 1
            self._loaded = False
            self.on_device_changed()
        code, text = describe_state(self.monitor.state, device, self.fastboot_ok)
        self._banner_code = code
        if text:
            first, second, icon = BANNER_BUTTONS.get(code, (None, None, FIF.INFO))
            self.banner.show_message(text.replace("\n", "<br>"), tr(*first) if first else None,
                                     tr(*second) if second else None, icon)
        else:
            self.banner.setVisible(False)
        self.update_actions()
        self._ensure_loaded()

    def _banner_action(self, which):
        first, second, _icon = BANNER_BUTTONS.get(self._banner_code, (None, None, None))
        label = (first, second)[which - 1]
        if label is None:
            return
        name = label[1]
        if name == "Restart ADB server":
            self.banner.btn1.setEnabled(False)
            self.banner.btn2.setEnabled(False)

            def finish(*_args):
                self.banner.btn1.setEnabled(True)
                self.banner.btn2.setEnabled(True)

            def failed(error):
                finish()
                toast(self, "err", tr("No se pudo reiniciar ADB", "Could not restart ADB"), str(error), 7000)

            self.monitor.restart_server(on_done=finish, on_error=failed)
        elif name.startswith("Connect over Wi-Fi"):
            from .android_dialogs import WifiDialog
            WifiDialog(self.monitor, self.window()).exec()
        else:
            self.monitor.refresh()

    def run_task(self, work, done=None, fail=None, ok_title=None, ok_text="", err_title=None):
        self._tasks += 1
        self.devbar.set_busy(True)
        self.update_actions()

        def finish():
            self._tasks -= 1
            if self._tasks == 0:
                self.devbar.set_busy(False)
            self.update_actions()

        def on_done(result):
            finish()
            if ok_title:
                toast(self, "ok", ok_title, ok_text)
            if done:
                done(result)

        def on_fail(error):
            finish()
            toast(self, "err", err_title or tr("Error de ADB", "ADB error"), short_error(error), 8000)
            if fail:
                fail(error)

        run_async(work, on_done, on_fail)


def short_error(error):
    return android.short_text(str(error))


def set_action_text(action, es, en):
    text = tr(es, en)
    action._es_en = (es, en)
    if action.text() == text:
        return False
    action.setText(text)
    return True


def relayout_bar(bar):
    for button in bar.commandButtons:
        button.updateGeometry()
    if bar.layout():
        bar.layout().invalidate()
    bar.updateGeometry()
    bar.update()


def confirm(parent, title, text, ok=None, danger=False):
    box = MessageBox(title, text, parent.window())
    box.yesButton.setText(ok or tr("Aceptar", "OK"))
    box.cancelButton.setText(tr("Cancelar", "Cancel"))
    if danger:
        box.yesButton.setStyleSheet(DANGER_BUTTON)
    return bool(box.exec())


class ChoiceDialog(MessageBoxBase):

    def __init__(self, title, text, choices, parent=None, ok=None):
        super().__init__(parent)
        self.viewLayout.addWidget(SubtitleLabel(title))
        label = BodyLabel(text)
        label.setWordWrap(True)
        self.viewLayout.addWidget(label)
        self.combo = ComboBox()
        for label_text, value in choices:
            self.combo.addItem(label_text, userData=value)
        self.combo.setMinimumWidth(280)
        self.viewLayout.addWidget(self.combo)
        self.yesButton.setText(ok or tr("Aceptar", "OK"))
        self.cancelButton.setText(tr("Cancelar", "Cancel"))
        self.widget.setMinimumWidth(380)

    def value(self):
        return self.combo.currentData()


def ask_choice(parent, title, text, choices, ok=None):
    dialog = ChoiceDialog(title, text, choices, parent.window(), ok)
    return dialog.value() if dialog.exec() else None

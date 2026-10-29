import threading
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QStackedWidget, QVBoxLayout,
                               QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, FluentIcon as FIF, LineEdit, MessageBoxBase, PrimaryPushButton,
                            ProgressBar, PushButton, SegmentedWidget, SubtitleLabel)

from .. import theme
from ..core import android
from ..dispatch import post, run_async
from ..i18n import tr
from .components import toast


class WifiDialog(MessageBoxBase):

    def __init__(self, monitor, parent=None):
        super().__init__(parent)
        self.monitor = monitor
        self._working = False
        self.viewLayout.addWidget(SubtitleLabel(tr("Conectar por Wi-Fi", "Connect over Wi-Fi")))
        note = CaptionLabel(tr("El móvil y el PC tienen que estar en la misma red Wi-Fi.",
                               "The phone and this computer must be on the same Wi-Fi network."))
        note.setStyleSheet(f"color:{theme.MUTED}")
        self.viewLayout.addWidget(note)

        self.tabs = SegmentedWidget()
        self.pages = QStackedWidget()
        for index, (key, es, en) in enumerate((("cable", "Desde el cable", "From the cable"),
                                               ("pair", "Emparejar (Android 11+)", "Pair (Android 11+)"),
                                               ("addr", "Dirección", "Address"))):
            self.tabs.addItem(key, tr(es, en), onClick=lambda _=False, i=index: self.pages.setCurrentIndex(i))
        self.viewLayout.addWidget(self.tabs)
        self.viewLayout.addWidget(self.pages)

        page, lay = self._page()
        lay.addWidget(self._text(tr(
            "Con el móvil conectado por USB, VeyloraDevice activa ADB por Wi-Fi y se conecta sola. "
            "Después puedes desenchufar el cable.",
            "With the phone plugged in over USB, VeyloraDevice turns on ADB over Wi-Fi and connects by itself. "
            "Then you can unplug the cable.")))
        self.cable_button = PrimaryPushButton(FIF.WIFI, tr("Activar y conectar", "Enable and connect"))
        self.cable_button.clicked.connect(self._from_cable)
        lay.addWidget(self.cable_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.pages.addWidget(page)

        page, lay = self._page()
        lay.addWidget(self._text(tr(
            "En el móvil: Opciones de desarrollador → Depuración inalámbrica → «Vincular dispositivo con código de "
            "sincronización». Escribe aquí la dirección y el código que muestra.",
            "On the phone: Developer options → Wireless debugging → “Pair device with pairing code”. "
            "Enter the address and code it shows here.")))
        self.pair_address = LineEdit()
        self.pair_address.setPlaceholderText(tr("Dirección de emparejamiento  192.168.1.20:37123",
                                                "Pairing address  192.168.1.20:37123"))
        self.pair_code = LineEdit()
        self.pair_code.setPlaceholderText(tr("Código de 6 dígitos", "6-digit code"))
        self.pair_code.setMaxLength(6)
        self.pair_button = PrimaryPushButton(FIF.LINK, tr("Emparejar", "Pair"))
        self.pair_button.clicked.connect(self._pair)
        lay.addWidget(self.pair_address)
        lay.addWidget(self.pair_code)
        lay.addWidget(self.pair_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.pages.addWidget(page)

        page, lay = self._page()
        lay.addWidget(self._text(tr(
            "Escribe la dirección que aparece en la pantalla principal de «Depuración inalámbrica» "
            "(o la IP del móvil con el puerto 5555).",
            "Enter the address shown on the main “Wireless debugging” screen "
            "(or the phone's IP with port 5555).")))
        self.address = LineEdit()
        self.address.setPlaceholderText("192.168.1.20:5555")
        self.address.returnPressed.connect(self._connect)
        self.connect_button = PrimaryPushButton(FIF.CONNECT, tr("Conectar", "Connect"))
        self.connect_button.clicked.connect(self._connect)
        self.disconnect_button = PushButton(FIF.CLOSE, tr("Desconectar los de Wi-Fi", "Disconnect Wi-Fi devices"))
        self.disconnect_button.clicked.connect(self._disconnect)
        row = QHBoxLayout()
        row.addWidget(self.connect_button)
        row.addWidget(self.disconnect_button)
        row.addStretch(1)
        lay.addWidget(self.address)
        lay.addLayout(row)
        self.pages.addWidget(page)

        self.status = CaptionLabel("")
        self.status.setWordWrap(True)
        self.viewLayout.addWidget(self.status)
        self.tabs.setCurrentItem("cable")
        self.yesButton.hide()
        self.cancelButton.setText(tr("Cerrar", "Close"))
        self.widget.setMinimumWidth(480)
        self._update_cable_button()

    @staticmethod
    def _page():
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)
        return page, lay

    @staticmethod
    def _text(text):
        label = BodyLabel(text)
        label.setWordWrap(True)
        return label

    def _usb_serial(self):
        device = self.monitor.current()
        if device and device["status"] == "device" and ":" not in device["serial"]:
            return device["serial"]
        return None

    def _update_cable_button(self):
        self.cable_button.setEnabled(bool(self._usb_serial()) and not self._working)
        if not self._usb_serial():
            self._say(tr("Selecciona un móvil conectado por USB para usar esta opción.",
                         "Select a phone connected over USB to use this option."), "muted")

    def _say(self, text, kind="muted"):
        color = {"ok": theme.OK, "err": theme.DANGER}.get(kind, theme.MUTED)
        self.status.setStyleSheet(f"color:{color}")
        self.status.setText(text)

    def _work(self, fn, on_ok, start_text):
        if self._working:
            return
        self._working = True
        for button in (self.cable_button, self.pair_button, self.connect_button, self.disconnect_button):
            button.setEnabled(False)
        self._say(start_text)

        def finish():
            self._working = False
            for button in (self.pair_button, self.connect_button, self.disconnect_button):
                button.setEnabled(True)
            self._update_cable_button()

        def done(result):
            finish()
            on_ok(result)

        def failed(error):
            finish()
            self._say(str(error), "err")

        run_async(fn, done, failed)

    def _from_cable(self):
        serial = self._usb_serial()
        if not serial:
            return

        def work():
            address = android.enable_tcpip(serial)
            android.connect_wifi(address)
            return address

        def ok(address):
            self._say(tr(f"Conectado a {address}. Ya puedes desenchufar el cable.",
                         f"Connected to {address}. You can unplug the cable now."), "ok")
            self.monitor.refresh()

        self._work(work, ok, tr("Activando ADB por Wi-Fi…", "Turning on ADB over Wi-Fi…"))

    def _pair(self):
        address, code = self.pair_address.text(), self.pair_code.text()
        self._work(lambda: android.pair_wifi(address, code), self._paired, tr("Emparejando…", "Pairing…"))

    def _paired(self, _output):
        self._say(tr("Emparejado. Ahora conecta con la dirección de la pantalla principal de Depuración "
                     "inalámbrica.", "Paired. Now connect using the address on the main Wireless debugging screen."),
                  "ok")
        self.tabs.setCurrentItem("addr")
        self.pages.setCurrentIndex(2)
        self.address.setFocus()

    def _connect(self):
        address = self.address.text()

        def ok(output):
            self._say(output, "ok")
            self.monitor.refresh()

        self._work(lambda: android.connect_wifi(address), ok, tr("Conectando…", "Connecting…"))

    def _disconnect(self):
        def ok(_result):
            self._say(tr("Desconectado.", "Disconnected."), "ok")
            self.monitor.refresh()

        self._work(android.disconnect_wifi, ok, tr("Desconectando…", "Disconnecting…"))


class ScreenshotDialog(MessageBoxBase):

    def __init__(self, png_bytes, suggested_name, parent=None):
        super().__init__(parent)
        self.png = png_bytes
        self.suggested_name = suggested_name
        self.saved_path = None
        self.viewLayout.addWidget(SubtitleLabel(tr("Captura de pantalla", "Screenshot")))
        pixmap = QPixmap()
        pixmap.loadFromData(png_bytes)
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not pixmap.isNull():
            preview.setPixmap(pixmap.scaled(360, 560, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
        self.viewLayout.addWidget(preview)
        copy_button = PushButton(FIF.COPY, tr("Copiar imagen", "Copy image"))
        copy_button.clicked.connect(lambda: self._copy(pixmap))
        self.viewLayout.addWidget(copy_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self.yesButton.setText(tr("Guardar como…", "Save as…"))
        self.cancelButton.setText(tr("Cerrar", "Close"))
        self.widget.setMinimumWidth(420)

    def _copy(self, pixmap):
        QGuiApplication.clipboard().setPixmap(pixmap)
        toast(self, "ok", tr("Copiada", "Copied"), tr("La captura está en el portapapeles.",
                                                      "The screenshot is on the clipboard."), 2500)

    def validate(self):
        start = str(Path.home() / "Pictures" / self.suggested_name)
        path, _ = QFileDialog.getSaveFileName(self, tr("Guardar captura", "Save screenshot"), start,
                                              "PNG (*.png)")
        if not path:
            return False
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            Path(path).write_bytes(self.png)
        except OSError as exc:
            toast(self, "err", tr("No se pudo guardar", "Could not save"), str(exc), 6000)
            return False
        self.saved_path = path
        return True


class BatchDialog(MessageBoxBase):

    def __init__(self, title, items, worker, describe, parent=None):
        super().__init__(parent)
        self.items, self.worker, self.describe = list(items), worker, describe
        self.results = []
        self._cancel = False
        self._finished = False
        self._started = False
        self.viewLayout.addWidget(SubtitleLabel(title))
        self.current = BodyLabel("")
        self.current.setWordWrap(True)
        self.viewLayout.addWidget(self.current)
        self.progress = ProgressBar()
        self.progress.setRange(0, max(1, len(self.items)))
        self.viewLayout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(190)
        self.log.setStyleSheet("QPlainTextEdit { background:#0e0f12; color:#cfd3da; border:1px solid #2b2f35; "
                               "border-radius:8px; padding:6px; font-size:12px; }")
        self.viewLayout.addWidget(self.log)
        self.yesButton.hide()
        self.yesButton.setText(tr("Cerrar", "Close"))
        self.cancelButton.setText(tr("Cancelar", "Cancel"))
        self.widget.setMinimumWidth(600)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._started:
            self._started = True
            threading.Thread(target=self._run, daemon=True).start()

    def reject(self):
        if self._finished:
            super().reject()
        else:
            self._cancel = True
            self.current.setText(tr("Cancelando… termina el elemento en curso y para.",
                                    "Cancelling… the current item will finish, then it stops."))

    def _run(self):
        for index, item in enumerate(self.items):
            if self._cancel:
                break
            post(lambda i=index, it=item: self.current.setText(
                tr(f"({i + 1} de {len(self.items)}) {self.describe(it)}", f"({i + 1} of {len(self.items)}) {self.describe(it)}")))
            try:
                self.worker(item)
                error = None
            except Exception as exc:
                error = exc
            post(lambda i=index, it=item, e=error: self._item_done(i, it, e))
        post(self._all_done)

    def _item_done(self, index, item, error):
        self.results.append((item, error))
        mark = "✔" if error is None else "✘"
        detail = "" if error is None else f" — {android.short_text(str(error), lines=2, chars=200)}"
        self.log.appendPlainText(f"{mark} {self.describe(item)}{detail}")
        self.progress.setValue(index + 1)

    def _all_done(self):
        self._finished = True
        good = sum(1 for _item, error in self.results if error is None)
        bad = len(self.results) - good
        skipped = len(self.items) - len(self.results)
        text = tr(f"Terminado: {good} correctas, {bad} con error", f"Done: {good} succeeded, {bad} failed")
        if skipped:
            text += tr(f" y {skipped} sin hacer (cancelado).", f" and {skipped} not done (cancelled).")
        self.current.setText(text)
        self.progress.setValue(len(self.results))
        self.cancelButton.hide()
        self.yesButton.show()


def run_batch(parent, title, items, worker, describe):
    dialog = BatchDialog(title, items, worker, describe, parent.window())
    dialog.exec()
    return dialog.results

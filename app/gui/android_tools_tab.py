import shutil
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QMessageBox
from qfluentwidgets import BodyLabel, CaptionLabel, FluentIcon as FIF, LineEdit, PushButton, SwitchButton

from .. import i18n, theme
from ..core import android, requirements
from ..core.terminal import launch_in_terminal
from ..dispatch import run_async
from ..i18n import tr
from .android_base import AndroidPage, ask_choice, confirm, short_error
from .android_dialogs import ScreenshotDialog, WifiDialog
from .android_logcat import LogcatWindow
from .components import ToolCard, card_frame, section, toast
from .widgets import LogPanel

KEY_BUTTONS = (("back", FIF.LEFT_ARROW, "Atrás", "Back"), ("home", FIF.HOME, "Inicio", "Home"),
               ("recents", FIF.APPLICATION, "Recientes", "Recents"), ("power", FIF.POWER_BUTTON, "Pantalla", "Screen"),
               ("volume_down", FIF.REMOVE, "Vol −", "Vol −"), ("volume_up", FIF.ADD, "Vol +", "Vol +"),
               ("mute", FIF.MUTE, "Silenciar", "Mute"), ("play_pause", FIF.PLAY, "Play/Pausa", "Play/Pause"),
               ("notifications", getattr(FIF, "RINGER", FIF.INFO), "Notificaciones", "Notifications"),
               ("quick_settings", FIF.SETTING, "Ajustes rápidos", "Quick settings"))
RECORD_CHOICES = ((10, "10 segundos", "10 seconds"), (30, "30 segundos", "30 seconds"),
                  (60, "1 minuto", "1 minute"), (180, "3 minutos (máximo)", "3 minutes (maximum)"))


class AndroidToolsTab(AndroidPage):

    goto_device = Signal()
    goto_apps = Signal()
    goto_files = Signal()
    open_report = Signal()

    def __init__(self, monitor, parent=None):
        super().__init__("android-tools", ("Herramientas", "Tools"),
                         ("Información, capturas, control del móvil, copias, apps y conexión.",
                          "Information, screenshots, phone control, backups, apps and connection."),
                         monitor, scroll=True, parent=parent)
        self._windows = []
        self.panel = LogPanel()
        self.panel.setMinimumHeight(240)
        self.panel.setVisible(False)

        def group(es, en, items):
            self.body.addWidget(section(es, en))
            grid = QGridLayout()
            grid.setSpacing(10)
            for i, (icon, title, desc, fn) in enumerate(items):
                card = ToolCard(icon, title, desc)
                card.clicked.connect(lambda *_, f=fn: f())
                grid.addWidget(card, i // 2, i % 2)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            self.body.addLayout(grid)

        group("Información", "Information", [
            (FIF.INFO, ("Información completa", "Full information"),
             ("Todos los datos del dispositivo, ordenados", "Every device detail, organised"), self.goto_device.emit),
            (FIF.APPLICATION, ("Aplicaciones instaladas", "Installed apps"),
             ("Paquete, tipo y estado de cada app", "Package, type and state of every app"), self.goto_apps.emit),
            (FIF.DOCUMENT, ("Informe PDF", "PDF report"),
             ("Genera un PDF con los datos del móvil", "Create a PDF with the phone's data"), self.open_report.emit),
            (FIF.HISTORY, ("Registro del sistema (logcat)", "System log (logcat)"),
             ("Log del móvil en vivo con filtros", "Live phone log with filters"), self._logcat),
        ])
        group("Pantalla", "Screen", [
            (FIF.CAMERA, ("Captura de pantalla", "Screenshot"),
             ("Haz una captura y guárdala o cópiala", "Take a screenshot to save or copy"), self._screenshot),
            (FIF.VIDEO, ("Grabar pantalla", "Record screen"),
             ("Vídeo MP4 de hasta 3 minutos", "MP4 video up to 3 minutes"), self._record),
            (FIF.VIEW, ("Ver y controlar la pantalla", "Mirror and control the screen"),
             ("Abre scrcpy si lo tienes instalado", "Opens scrcpy if you have it installed"), self._mirror),
        ])

        self.body.addWidget(section("Control del móvil", "Phone control"))
        remote, rl = card_frame(spacing=10)
        grid = QGridLayout()
        grid.setSpacing(8)
        for index, (key, icon, es, en) in enumerate(KEY_BUTTONS):
            button = PushButton(icon, "")
            i18n.bind(button, "setText", es, en)
            button.clicked.connect(lambda _=False, k=key: self._key(k))
            grid.addWidget(button, index // 5, index % 5)
        for column in range(5):
            grid.setColumnStretch(column, 1)
        rl.addLayout(grid)
        self.input_note = CaptionLabel("")
        self.input_note.setWordWrap(True)
        self.input_note.setStyleSheet(f"color:{theme.WARN}")
        i18n.bind(self.input_note, "setText",
                  "Este móvil bloquea Atrás, Recientes, Pantalla y escribir desde el PC (Inicio, volumen, "
                  "multimedia y notificaciones sí funcionan).",
                  "This phone blocks Back, Recents, Screen and typing from the computer (Home, volume, media and "
                  "notifications still work).")
        self.input_fix = PushButton(FIF.SETTING, "")
        i18n.bind(self.input_fix, "setText", "Cómo activarlo", "How to enable it")
        self.input_fix.clicked.connect(self._input_help)
        self.input_row = QHBoxLayout()
        self.input_row.addWidget(self.input_note, 1)
        self.input_row.addWidget(self.input_fix)
        rl.addLayout(self.input_row)
        self._set_input_note(False)
        self.text_edit = self._input_row(
            rl, ("Escribir en el móvil (el campo de texto debe estar activo)",
                 "Type on the phone (a text field must be active)"), FIF.SEND, self._type)
        self.url_edit = self._input_row(
            rl, ("Abrir un enlace en el móvil: https://…", "Open a link on the phone: https://…"),
            FIF.LINK, self._open_url)
        self.body.addWidget(remote)

        group("Copias y apps", "Backups and apps", [
            (FIF.SAVE, ("Copia de seguridad…", "Back up device…"),
             ("Copia todo el almacenamiento a una carpeta", "Copy all storage to a folder"), self._backup),
            (FIF.ADD, ("Instalar app (.apk)…", "Install app (.apk)…"),
             ("Instala un archivo APK en el dispositivo", "Install an APK file on the device"), self._install),
            (FIF.FOLDER, ("Explorar archivos", "Browse files"),
             ("Sube, descarga y organiza archivos del móvil", "Upload, download and organise phone files"),
             self.goto_files.emit),
        ])
        group("Conexión", "Connection", [
            (FIF.WIFI, ("Conectar por Wi-Fi…", "Connect over Wi-Fi…"),
             ("Sin cable: con el USB, con código o con la dirección", "Cable-free: via USB, pairing code or address"),
             self._wifi),
            (FIF.ROTATE, ("Reiniciar servidor ADB", "Restart ADB server"),
             ("Arréglalo si el móvil no aparece o sale sin conexión", "Fixes a phone that does not show up or is offline"),
             self._restart_server),
            (FIF.DEVELOPER_TOOLS, ("Instalar requisitos", "Install requirements"),
             ("Instala ADB y scrcpy en el PC (pide tu contraseña)", "Installs ADB and scrcpy on this PC (asks for your password)"),
             self._install_requirements),
            (FIF.COMMAND_PROMPT, ("Terminal ADB (shell)", "ADB terminal (shell)"),
             ("Abre una terminal conectada al móvil", "Opens a terminal connected to the phone"), self._shell),
        ])

        term_card, tl = card_frame(QHBoxLayout)
        tl.addWidget(i18n.bind(BodyLabel(), "setText", "Mostrar la salida de copias/instalaciones en una terminal externa",
                               "Show backup/install output in an external terminal"), 1)
        self.chk_term = SwitchButton()
        self._set_term_texts()
        i18n.on_change(lambda _c: self._set_term_texts())
        tl.addWidget(self.chk_term)
        self.body.addWidget(term_card)
        self.out_lbl = section("Salida de la operación", "Operation output")
        self.out_lbl.setVisible(False)
        self.body.addWidget(self.out_lbl)
        self.body.addWidget(self.panel)
        self.body.addStretch(1)
        self.finish_setup()

    def _input_row(self, parent_layout, placeholder, icon, handler):
        row = QHBoxLayout()
        row.setSpacing(8)
        edit = LineEdit()
        i18n.bind(edit, "setPlaceholderText", *placeholder)
        edit.setClearButtonEnabled(True)
        edit.returnPressed.connect(handler)
        button = PushButton(icon, "")
        i18n.bind(button, "setText", "Enviar", "Send")
        button.clicked.connect(handler)
        row.addWidget(edit, 1)
        row.addWidget(button)
        parent_layout.addLayout(row)
        return edit

    def _set_term_texts(self):
        self.chk_term.setOnText(tr("Sí", "On"))
        self.chk_term.setOffText(tr("No", "Off"))

    def _show_panel(self):
        self.out_lbl.setVisible(True)
        self.panel.setVisible(True)

    def _need_device(self):
        if self.ready and self.device["status"] == "device":
            return self.serial
        toast(self, "warn", tr("Sin dispositivo", "No device"),
              tr("Conecta un Android y acepta la depuración USB primero.",
                 "Connect an Android and accept USB debugging first."))
        return None

    def _run(self, prog, args):
        if self.chk_term.isChecked():
            if not launch_in_terminal([prog] + list(args)):
                QMessageBox.warning(self, "Terminal", tr("No encontré ningún terminal. Desactiva la opción para ver la salida aquí.",
                                                         "No terminal found. Turn the option off to see output here."))
            return
        self._show_panel()
        if not self.panel.run(prog, args):
            toast(self, "warn", tr("Ocupado", "Busy"), tr("Ya hay una operación en curso. Espera a que termine.",
                                                           "An operation is already running. Wait for it to finish."))

    def _install(self):
        serial = self._need_device()
        if not serial:
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("Elegir APK", "Choose APK"), "", "Android (*.apk)")
        if path:
            self._run("adb", ["-s", serial, "install", "-r", path])

    def _backup(self):
        serial = self._need_device()
        if not serial:
            return
        folder = QFileDialog.getExistingDirectory(self, tr("Carpeta destino de la copia", "Backup destination folder"))
        if folder:
            self._run("adb", ["-s", serial, "pull", "/sdcard", folder])

    def _screenshot(self):
        serial = self._need_device()
        if not serial:
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")

        def shown(png):
            ScreenshotDialog(png, f"android-{stamp}.png", self.window()).exec()

        self.run_task(lambda: android.screenshot(serial), done=shown,
                      err_title=tr("No se pudo capturar", "Could not capture"))

    def _record(self):
        serial = self._need_device()
        if not serial:
            return
        seconds = ask_choice(
            self, tr("Grabar pantalla", "Record screen"),
            tr("Deja el móvil encendido y desbloqueado y no lo desconectes mientras graba.",
               "Keep the phone on and unlocked and do not unplug it while recording."),
            [(tr(es, en), value) for value, es, en in RECORD_CHOICES], ok=tr("Elegir destino", "Choose destination"))
        if not seconds:
            return
        default = Path.home() / "Videos" / f"android-{time.strftime('%Y%m%d-%H%M%S')}.mp4"
        path, _ = QFileDialog.getSaveFileName(self, tr("Guardar grabación", "Save recording"), str(default),
                                              "MP4 (*.mp4)")
        if not path:
            return
        if not path.lower().endswith(".mp4"):
            path += ".mp4"
        toast(self, "info", tr("Grabando…", "Recording…"),
              tr(f"Durará {seconds} s. No desconectes el móvil.", f"It will last {seconds} s. Do not unplug the phone."),
              4000)
        self.run_task(lambda: android.record_screen(serial, path, seconds),
                      ok_title=tr("Grabación guardada", "Recording saved"), ok_text=path,
                      err_title=tr("No se pudo grabar", "Could not record"))

    def _mirror(self):
        serial = self._need_device()
        if not serial:
            return
        if not shutil.which("scrcpy"):
            self._offer_install(["scrcpy"])
            return
        self.run_task(lambda: android.input_allowed(serial), done=lambda allowed: self._launch_scrcpy(serial, allowed))

    def _launch_scrcpy(self, serial, allowed):
        self._set_input_note(not allowed)
        if not allowed:
            self._input_help()
        subprocess.Popen([shutil.which("scrcpy"), "-s", serial], start_new_session=True)

    def _offer_install(self, missing):
        names = ", ".join(missing)
        command = requirements.install_script(missing)
        if confirm(self, tr("Falta " + names, "Missing " + names),
                   tr(f"{names} no está instalado. ¿Instalarlo ahora? Se abre una terminal y te pide tu contraseña.\n\n"
                      f"Se ejecutará:\n{command.replace(' && ', chr(10))}",
                      f"{names} is not installed. Install it now? A terminal opens and asks for your password.\n\n"
                      f"This will run:\n{command.replace(' && ', chr(10))}"),
                   ok=tr("Instalar", "Install")):
            self._run_install(command)

    def _run_install(self, command):
        if not command:
            toast(self, "ok", tr("Todo instalado", "Everything installed"),
                  tr("ADB y scrcpy ya están en el PC.", "ADB and scrcpy are already on this PC."))
        elif not launch_in_terminal(["bash", "-c", command]):
            toast(self, "err", tr("Sin terminal", "No terminal"),
                  tr("No encontré ningún terminal. Copia esto en uno: ", "No terminal found. Paste this into one: ")
                  + command, 12000)

    def _install_requirements(self):
        self._run_install(requirements.install_script(requirements.missing_tools()))

    def _quick(self, fn):
        def failed(error):
            if isinstance(error, android.InputBlockedError):
                self._set_input_note(True)
                self._input_help()
            else:
                toast(self, "err", tr("No se pudo enviar", "Could not send"), short_error(error), 9000)

        run_async(fn, None, failed)

    def _set_input_note(self, blocked):
        self.input_note.setVisible(blocked)
        self.input_fix.setVisible(blocked)

    def on_device_changed(self):
        self._set_input_note(False)

    def load(self):
        serial = self.serial
        if self.device and self.device["status"] == "device":
            run_async(lambda: android.input_allowed(serial), self.guard(lambda ok: self._set_input_note(not ok)),
                      lambda _e: None)

    def _input_help(self):
        serial = self._need_device()
        if not serial:
            return
        if confirm(self, tr("Activar el control desde el PC", "Allow control from the computer"),
                   tr("Este móvil (típico de Xiaomi, Redmi y POCO) bloquea que el PC pulse Atrás, Recientes o "
                      "escriba. Para permitirlo:\n\n"
                      "1. Pulsa «Abrir ajustes»: se abrirá Opciones de desarrollador en el móvil.\n"
                      "2. Activa «Depuración USB (ajustes de seguridad)». Puede pedir iniciar sesión con tu cuenta Mi "
                      "y tener una SIM puesta.\n"
                      "3. Acepta el aviso y vuelve a pulsar el botón aquí.\n\n"
                      "Mientras tanto, Inicio, volumen, multimedia y notificaciones ya funcionan sin ese ajuste.",
                      "This phone (typical of Xiaomi, Redmi and POCO) blocks the computer from pressing Back, "
                      "Recents or typing. To allow it:\n\n"
                      "1. Press “Open settings”: Developer options will open on the phone.\n"
                      "2. Turn on “USB debugging (Security settings)”. It may ask you to sign in with your Mi "
                      "account and to have a SIM inserted.\n"
                      "3. Accept the prompt and press the button here again.\n\n"
                      "Meanwhile Home, volume, media and notifications already work without that setting."),
                   ok=tr("Abrir ajustes", "Open settings")):
            self._quick(lambda: android.open_developer_options(serial))

    def _key(self, key):
        serial = self._need_device()
        if serial:
            self._quick(lambda: android.send_key(serial, key))

    def _type(self):
        text = self.text_edit.text()
        serial = self._need_device() if text else None
        if serial:
            self._quick(lambda: android.send_text(serial, text))
            self.text_edit.clear()

    def _open_url(self):
        url = self.url_edit.text()
        serial = self._need_device() if url else None
        if serial:
            self._quick(lambda: android.open_url(serial, url))

    def _wifi(self):
        WifiDialog(self.monitor, self.window()).exec()

    def _restart_server(self):
        self.run_task(android.restart_server, done=lambda _r: self.monitor.refresh(),
                      ok_title=tr("Servidor ADB reiniciado", "ADB server restarted"),
                      err_title=tr("No se pudo reiniciar ADB", "Could not restart ADB"))

    def _shell(self):
        serial = self._need_device()
        if serial and not launch_in_terminal(["adb", "-s", serial, "shell"]):
            toast(self, "err", tr("Sin terminal", "No terminal"),
                  tr("No encontré ningún terminal instalado.", "No installed terminal found."))

    def _logcat(self):
        serial = self._need_device()
        if not serial:
            return
        window = LogcatWindow(serial, self.window())
        self._windows = [w for w in self._windows if w.isVisible()] + [window]
        window.show()

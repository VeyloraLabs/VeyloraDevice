import glob
import os
import shutil
import zipfile

from PySide6.QtWidgets import QButtonGroup, QFileDialog, QHBoxLayout, QMessageBox, QVBoxLayout
from qfluentwidgets import (BodyLabel, CaptionLabel, ComboBox, FluentIcon as FIF, IconWidget, PushButton,
                            RadioButton, StrongBodyLabel, SwitchButton)

from .. import i18n, privacy, settings, theme
from ..i18n import tr
from .components import Page, Pill, card_frame, section, toast
from .widgets import LogPanel


class FlashTab(Page):
    def __init__(self, monitor, parent=None):
        super().__init__("flash", ("Flasheo", "Flash"),
                         ("Actualiza o restaura el dispositivo.",
                          "Update or restore the device."), scroll=True, parent=parent)
        self.monitor = monitor

        dev_card, dl = card_frame(QHBoxLayout, spacing=14)
        self.dev_icon = IconWidget(FIF.PHONE)
        self.dev_icon.setFixedSize(30, 30)
        self.dev_label = StrongBodyLabel("")
        self.dev_pill = Pill("", "muted")
        dl.addWidget(self.dev_icon)
        dl.addWidget(self.dev_label, 1)
        dl.addWidget(self.dev_pill)
        self.body.addWidget(dev_card)

        self.body.addWidget(section("1 · Firmware", "1 · Firmware"))
        fw_card, fl = card_frame()
        self.rb_file = RadioButton()
        self.rb_latest = RadioButton()
        i18n.bind(self.rb_file, "setText", "Archivo IPSW", "IPSW file")
        i18n.bind(self.rb_latest, "setText", "Última versión firmada", "Latest signed version")
        self.rb_file.setChecked(True)
        g1 = QButtonGroup(self)
        g1.addButton(self.rb_file)
        g1.addButton(self.rb_latest)
        self.combo = ComboBox()
        self.combo.setEditable(True) if hasattr(self.combo, "setEditable") else None
        self.combo.setMinimumWidth(300)
        b_browse = PushButton(FIF.FOLDER, "")
        i18n.bind(b_browse, "setText", "Examinar…", "Browse…")
        b_reload = PushButton(FIF.SYNC, "")
        b_reload.setToolTip(tr("Releer la carpeta de descargas", "Rescan the downloads folder"))
        b_browse.clicked.connect(self._browse)
        b_reload.clicked.connect(self.refresh_local)
        self.rb_latest.toggled.connect(lambda on: self.combo.setEnabled(not on))
        row = QHBoxLayout()
        row.addWidget(self.combo, 1)
        row.addWidget(b_browse)
        row.addWidget(b_reload)
        fl.addWidget(self.rb_file)
        fl.addLayout(row)
        fl.addWidget(self.rb_latest)
        self.body.addWidget(fw_card)

        self.body.addWidget(section("2 · Modo", "2 · Mode"))
        mode_card, ml = card_frame()
        self.rb_update = RadioButton()
        self.rb_erase = RadioButton()
        i18n.bind(self.rb_update, "setText", "Actualizar", "Update")
        i18n.bind(self.rb_erase, "setText", "Restaurar", "Restore")
        self.rb_update.setChecked(True)
        g2 = QButtonGroup(self)
        g2.addButton(self.rb_update)
        g2.addButton(self.rb_erase)
        ml.addWidget(self.rb_update)
        ml.addWidget(self.rb_erase)
        self.body.addWidget(mode_card)

        self.body.addWidget(section("3 · Opciones", "3 · Options"))
        opt_card, ol = card_frame(spacing=10)
        self.chk_root = SwitchButton()
        self.chk_root.setChecked(True)
        self.chk_debug = SwitchButton()
        self._switches = (self.chk_root, self.chk_debug)
        self._set_switch_texts()
        i18n.on_change(lambda _c: self._set_switch_texts())
        for sw, es, en in ((self.chk_root, "Permisos de administrador", "Administrator permissions"),
                           (self.chk_debug, "Registro detallado", "Detailed log")):
            r = QHBoxLayout()
            r.addWidget(i18n.bind(BodyLabel(), "setText", es, en), 1)
            r.addWidget(sw)
            ol.addLayout(r)
        self.body.addWidget(opt_card)

        self.b_start = PushButton(FIF.PLAY, "")
        i18n.bind(self.b_start, "setText", "Iniciar flasheo", "Start flash")
        self.b_start.setStyleSheet(f"PushButton {{ background:{theme.DANGER}; color:white; border:none; border-radius:8px; padding:9px 22px 9px 40px; font-weight:600 }}"
                                   f"PushButton:hover {{ background:#f0565b }} PushButton:pressed {{ background:#c93a3f }}"
                                   f"PushButton:disabled {{ background:#3a2527; color:#888 }}")
        self.b_cancel = PushButton(FIF.CANCEL, "")
        i18n.bind(self.b_cancel, "setText", "Cancelar", "Cancel")
        self.b_cancel.setEnabled(False)
        self.b_start.clicked.connect(self.start)
        self.b_cancel.clicked.connect(self._cancel)
        btns = QHBoxLayout()
        btns.addWidget(self.b_start)
        btns.addWidget(self.b_cancel)
        btns.addStretch(1)
        self.body.addLayout(btns)

        self.panel = LogPanel()
        self.panel.setMinimumHeight(260)
        self.panel.setVisible(False)
        self.panel.finished.connect(self._finished)
        self.body.addWidget(self.panel)
        self.body.addStretch(1)

        monitor.changed.connect(self._on_state)
        i18n.on_change(lambda _c: self._on_state(self.monitor.state))
        privacy.bus.changed.connect(lambda: self._on_state(self.monitor.state))
        self._on_state(monitor.state)
        self.refresh_local()

    def _set_switch_texts(self):
        for sw in self._switches:
            sw.setOnText(tr("Sí", "On"))
            sw.setOffText(tr("No", "Off"))

    def _on_state(self, s):
        m = s["mode"]
        if m == "normal" and s.get("info"):
            i = s["info"]
            name = privacy.generic_name(i.get("DeviceName", "?"), "iPhone / iPad")
            self.dev_label.setText(f'{name} · {i.get("ProductType", "?")} · iOS {i.get("ProductVersion", "?")}')
            self.dev_pill.setText(tr("Modo normal", "Normal mode"))
            self.dev_pill.set_kind("ok")
        elif m == "normal":
            self.dev_label.setText(tr("Dispositivo detectado pero sin emparejar", "Device detected but not paired"))
            self.dev_pill.setText(tr("Sin confiar", "Not trusted"))
            self.dev_pill.set_kind("warn")
        elif m == "recovery":
            self.dev_label.setText(f'{s["recovery"].get("PRODUCT", "?")}')
            self.dev_pill.setText(s["recovery"].get("MODE", "Recovery/DFU"))
            self.dev_pill.set_kind("warn")
        else:
            self.dev_label.setText(tr("Ningún dispositivo conectado", "No device connected"))
            self.dev_pill.setText(tr("Desconectado", "Disconnected"))
            self.dev_pill.set_kind("muted")

    def _current_path(self):
        return self.combo.currentText().strip()

    def refresh_local(self):
        cur = self._current_path()
        self.combo.clear()
        files = sorted(glob.glob(os.path.join(settings.ipsw_dir(), "*.ipsw")))
        if files:
            self.combo.addItems(files)
        if cur and cur in files:
            self.combo.setCurrentText(cur)

    def set_ipsw(self, path):
        self.refresh_local()
        i = self.combo.findText(path)
        if i < 0:
            self.combo.addItem(path)
            i = self.combo.findText(path)
        self.combo.setCurrentIndex(i)
        self.rb_file.setChecked(True)

    def _browse(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("Elegir IPSW", "Choose IPSW"), settings.ipsw_dir(), "Firmware (*.ipsw)")
        if f:
            self.set_ipsw(f)

    def start(self):
        if self.panel.running():
            return
        s = self.monitor.state
        if s["mode"] == "none":
            toast(self, "warn", tr("Sin dispositivo", "No device"), tr("No detecto ningún dispositivo conectado.", "No connected device detected."))
            return
        path = self._current_path()
        latest = self.rb_latest.isChecked()
        if not latest:
            if not os.path.isfile(path) or not path.lower().endswith(".ipsw"):
                toast(self, "warn", tr("Falta el IPSW", "IPSW missing"), tr("Elige un archivo .ipsw válido.", "Choose a valid .ipsw file."))
                return
            try:
                with zipfile.ZipFile(path) as archive:
                    if not any(n.endswith("BuildManifest.plist") for n in archive.namelist()):
                        raise ValueError(tr("No se encuentra BuildManifest.plist", "BuildManifest.plist not found"))
            except Exception as exc:
                QMessageBox.warning(self, tr("IPSW no válido", "Invalid IPSW"),
                                    tr(f"No se ha podido validar el firmware. Puede estar incompleto o dañado.\n\nDetalle: {exc}",
                                       f"The firmware could not be validated. It may be incomplete or damaged.\n\nDetails: {exc}"))
                return
        if not shutil.which("idevicerestore"):
            QMessageBox.critical(self, tr("Falta idevicerestore", "idevicerestore missing"),
                                 tr("Instala idevicerestore y vuelve a abrir la aplicación. En Fedora: sudo dnf install idevicerestore",
                                    "Install idevicerestore and reopen the app. On Fedora: sudo dnf install idevicerestore"))
            return
        erase = self.rb_erase.isChecked()
        msg = "\n".join("• " + w for w in self._warnings(erase, latest, path))
        msg += tr("\n\nDurante el proceso el dispositivo pasará por Recovery y es normal. No desconectes el cable. "
                  "Si falla, la app mostrará el registro para diagnosticarlo.\n\n¿Continuar?",
                  "\n\nThe device will go through Recovery during the process; that is normal. Do not unplug the cable. "
                  "If it fails, the app will show the log so you can diagnose it.\n\nContinue?")
        ask = QMessageBox.warning if erase else QMessageBox.question
        if ask(self, tr("Confirmar flasheo", "Confirm flash"), msg,
               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
               QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return

        args = ["-y"]
        if self.chk_debug.isChecked():
            args.append("-d")
        if erase:
            args.append("-e")
        args.append("-l") if latest else args.append(path)
        prog = "idevicerestore"
        if self.chk_root.isChecked():
            args, prog = [prog] + args, "pkexec"

        self.panel.setVisible(True)
        self.panel.clear()
        if self.panel.run(prog, args):
            self.b_start.setEnabled(False)
            self.b_cancel.setEnabled(True)

    def _warnings(self, erase, latest, path):
        w = []
        if erase:
            w.append(tr("Has elegido RESTAURAR: esta opción BORRA TODO el dispositivo y no se puede deshacer.",
                        "You chose RESTORE: this ERASES everything on the device and cannot be undone."))
        else:
            w.append(tr("Has elegido ACTUALIZAR: esta opción conserva tus datos.",
                        "You chose UPDATE: this keeps your data."))
        if latest:
            w.append(tr("Has elegido la última versión firmada: se descargará sola, así que necesita internet y espacio libre.",
                        "You chose the latest signed version: it will be downloaded automatically, so it needs internet and free space."))
        else:
            w.append(tr(f"Has elegido el archivo IPSW «{os.path.basename(path)}»: tiene que ser exactamente el de este modelo y seguir firmado.",
                        f"You chose the IPSW file “{os.path.basename(path)}”: it must match this exact model and still be signed."))
        if self.chk_root.isChecked():
            w.append(tr("Has activado los permisos de administrador: te pedirá la contraseña (hace falta en algunos modos USB).",
                        "You enabled administrator permissions: you will be asked for your password (needed in some USB modes)."))
        if self.chk_debug.isChecked():
            w.append(tr("Has activado el registro detallado: el registro será mucho más largo.",
                        "You enabled the detailed log: the log will be much longer."))
        return w

    def _cancel(self):
        if QMessageBox.warning(self, tr("Cancelar", "Cancel"),
                               tr("Cancelar a mitad de un flasheo puede dejar el dispositivo en modo Recovery (se arregla volviendo a restaurar). ¿Cancelar?",
                                  "Cancelling mid-flash can leave the device in Recovery mode (fixed by restoring again). Cancel?"),
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                               QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.panel.stop()

    def _finished(self, code):
        self.b_start.setEnabled(True)
        self.b_cancel.setEnabled(False)
        self.monitor.refresh()
        if code == 0:
            toast(self, "ok", tr("Flasheo completado", "Flash complete"),
                  tr("Espera a que el dispositivo reinicie y complete la activación.",
                     "Wait for the device to reboot and finish activation."), 9000)
        else:
            QMessageBox.warning(self, tr("Flasheo no completado", "Flash not completed"),
                                tr(f"El flasheo terminó con el código {code}.\n\nRevisa el registro. Si el dispositivo sigue en la pantalla del cable: prueba otro cable de datos o puerto directo, evita concentradores, y verifica que el IPSW corresponde exactamente al modelo y sigue firmado. No repitas restauraciones a ciegas si el registro muestra un error concreto.",
                                   f"The flash exited with code {code}.\n\nCheck the log. If the device is still on the cable screen: try another data cable or a direct port, avoid hubs, and verify the IPSW matches the exact model and is still signed. Don't retry blindly if the log shows a specific error."))

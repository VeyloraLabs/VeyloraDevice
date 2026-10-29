from PySide6.QtWidgets import QFileDialog, QGridLayout, QMessageBox
from qfluentwidgets import CaptionLabel, FluentIcon as FIF, SwitchButton, BodyLabel
from PySide6.QtWidgets import QHBoxLayout

from .. import i18n, theme
from ..core import connection, device, tools
from ..core.tools import ToolMissing
from ..core.terminal import launch_in_terminal
from ..dispatch import run_async
from ..i18n import tr
from .components import Page, ToolCard, card_frame, section, toast
from .report_dialog import ReportDialog
from .viewers import AppsWindow, InfoWindow, SyslogWindow
from .widgets import LogPanel


class ExtrasTab(Page):

    def __init__(self, monitor, parent=None):
        super().__init__("tools", ("Herramientas", "Tools"),
                         ("Información, copias, apps y arreglos de conexión.", "Information, backups, apps and connection fixes."),
                         scroll=True, parent=parent)
        self.monitor = monitor
        self._wins = {}
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
             ("Todos los datos del dispositivo, ordenados", "Every device detail, organised"), lambda: self._open("info")),
            (FIF.APPLICATION, ("Aplicaciones instaladas", "Installed apps"),
             ("Nombre, identificador y versión", "Name, identifier and version"), lambda: self._open("apps")),
            (FIF.DOCUMENT, ("Informe PDF", "PDF report"),
             ("Elige los datos y genera un PDF", "Choose the data and create a PDF"), lambda: self._open("pdf")),
            (FIF.HISTORY, ("Registro del sistema (syslog)", "System log (syslog)"),
             ("Log del iPhone en vivo con filtros", "Live iPhone log with filters"), lambda: self._open("syslog")),
        ])
        group("Copias y apps", "Backups and apps", [
            (FIF.SAVE, ("Copia de seguridad…", "Back up device…"),
             ("Backup completo a una carpeta", "Full backup to a folder"), self._backup),
            (FIF.ADD, ("Instalar app (.ipa)…", "Install app (.ipa)…"),
             ("Instala un archivo IPA en el dispositivo", "Install an IPA file on the device"), self._install),
        ])
        group("Conexión", "Connection", [
            (FIF.SEND, ("Reenviar aviso de «Confiar»", "Resend “Trust” prompt"),
             ("Si el iPhone no ha preguntado", "If the iPhone has not asked"), lambda: self.monitor.request_pair()),
            (FIF.CERTIFICATE, ("Borrar emparejados", "Clear pairings"),
             ("Borra los emparejados guardados y empieza de nuevo", "Clear saved pairings and start again"),
             lambda: self._fix("reset_pairing", tr("Emparejado borrado. Reconecta el cable.", "Pairing cleared. Replug the cable."))),
            (FIF.CLOSE, ("Bloquear ipheth", "Block ipheth"),
             ("Evita que el módulo «internet por USB» acapare el iPhone", "Stop the USB-tethering driver claiming the iPhone"),
             lambda: self._fix("ipheth_block", tr("ipheth bloqueado. Reconecta el cable.", "ipheth blocked. Replug the cable."))),
            (FIF.CONNECT, ("Desbloquear ipheth", "Unblock ipheth"),
             ("Recupera el internet por USB", "Restore USB tethering"),
             lambda: self._fix("ipheth_unblock", tr("ipheth desbloqueado.", "ipheth unblocked."))),
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

    def _set_term_texts(self):
        self.chk_term.setOnText(tr("Sí", "On"))
        self.chk_term.setOffText(tr("No", "Off"))

    def _show_panel(self):
        self.out_lbl.setVisible(True)
        self.panel.setVisible(True)

    def _open(self, which):
        win = self._wins.get(which)
        if win is not None and win.isVisible():
            win.raise_()
            win.activateWindow()
            return
        if which == "info":
            win = InfoWindow(self.monitor, self, on_report=lambda: self._open("pdf"))
        elif which == "apps":
            win = AppsWindow(self.monitor, self)
        elif which == "syslog":
            win = SyslogWindow(self.monitor, self)
        else:
            win = ReportDialog(self.monitor, self)
        self._wins[which] = win
        win.show()

    def open_report(self):
        self._open("pdf")

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

    def _need_device(self):
        s = self.monitor.state
        if s["mode"] == "normal" and s.get("info"):
            return s["udid"]
        toast(self, "warn", tr("Sin dispositivo", "No device"),
              tr("Conecta un dispositivo y confía en este equipo primero.", "Connect a device and trust this computer first."))
        return None

    def _install(self):
        udid = self._need_device()
        if not udid:
            return
        f, _ = QFileDialog.getOpenFileName(self, tr("Elegir IPA", "Choose IPA"), "", "iOS apps (*.ipa)")
        if f:
            try:
                cmd = device.installer_cmd("install", udid, f)
            except ToolMissing as e:
                toast(self, "err", tr("Falta una herramienta", "Missing tool"), str(e), 7000)
                return
            self._run(cmd[0], cmd[1:])

    def _backup(self):
        udid = self._need_device()
        if not udid:
            return
        d = QFileDialog.getExistingDirectory(self, tr("Carpeta destino del backup", "Backup destination folder"))
        if d:
            self._run("idevicebackup2", ["-u", udid, "backup", d])

    def _fix(self, name, ok_msg):
        self._show_panel()
        self.panel.println(tr("Aplicando… (si sale la ventana de contraseña, escríbela)", "Applying… (enter your password if prompted)"))

        def done(res):
            rc, out, err = res
            if rc == 0:
                self.panel.println("✅ " + ok_msg)
                toast(self, "ok", tr("Hecho", "Done"), ok_msg)
                self.monitor.refresh()
            else:
                self.panel.println(tr(f"No se pudo aplicar (código {rc}) ", f"Could not apply (code {rc}) ")
                                   + (out + err).decode(errors="replace").strip())
                toast(self, "err", tr("No se pudo aplicar", "Could not apply"), f"({rc})", 7000)

        run_async(lambda: tools.run(connection.fix_cmd(name), timeout=180), done,
                  lambda e: self.panel.println(f"⚠️ {e}"))

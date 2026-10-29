from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QTableWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (CaptionLabel, CommandBar, FluentIcon as FIF, PrimaryPushButton, SearchLineEdit,
                            StrongBodyLabel, SubtitleLabel, TableWidget, Action)

from .. import assets, i18n, privacy, theme
from ..core import catalog, connection, infomap, live_stats, tools
from ..core.util import fmt_bytes
from ..dispatch import run_async
from ..i18n import tr
from .components import Banner, Page, Pill, card_frame, toast
from .device_image import DeviceImage
from .stat_strip import StatStrip


class DeviceTab(Page):
    goto_firmwares = Signal(str)
    open_report = Signal()

    def __init__(self, monitor, parent=None):
        super().__init__("device", ("Sin dispositivo", "No device"), ("", ""), parent=parent)
        self.monitor = monitor
        self.state = {"mode": "none"}
        self._rows = []
        self._reveal = privacy.Reveal()
        self._fix_issue = None
        self._img_ident = None

        self.banner = Banner()
        self.banner.btn1.clicked.connect(lambda: self._fix_action(1))
        self.banner.btn2.clicked.connect(lambda: self._fix_action(2))
        self.body.addWidget(self.banner)

        self.strip = StatStrip([("Batería", "Battery"), ("Temperatura", "Temperature"),
                                ("Almacenamiento libre", "Free storage"), ("Salud de la batería", "Battery health")])
        self.body.addWidget(self.strip)
        self._live = None
        self._live_udid = None
        self._live_busy = False
        self._live_tick_count = 0
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(3000)
        self._live_timer.timeout.connect(self._live_poll)

        self.bar = CommandBar()
        self.bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.a_refresh = self._act(FIF.SYNC, "Actualizar", "Refresh", self.monitor.refresh)
        self.bar.addSeparator()
        self.a_restart = self._act(FIF.ROTATE, "Reiniciar", "Restart",
                                   lambda: self._cmd(["idevicediagnostics", "restart"], tr("Reiniciando…", "Restarting…")))
        self.a_shutdown = self._act(FIF.POWER_BUTTON, "Apagar", "Shut down",
                                    lambda: self._cmd(["idevicediagnostics", "shutdown"], tr("Apagando…", "Shutting down…")))
        self.bar.addSeparator()
        self.a_recovery = self._act(FIF.DEVELOPER_TOOLS, "Entrar en Recovery", "Enter Recovery", self._toggle_recovery)
        self.bar.addSeparator()
        self.a_parts = self._act(FIF.TAG, "Componentes", "Components", self._show_component_details)
        self.a_pdf = self._act(FIF.DOCUMENT, "Informe PDF", "PDF report", self.open_report.emit)
        self.b_fw = PrimaryPushButton(FIF.DOWNLOAD, "")
        i18n.bind(self.b_fw, "setText", "Ver firmwares", "Browse firmware")
        self.b_fw.clicked.connect(lambda: self.goto_firmwares.emit(self.product()))
        self.body.addWidget(self.bar)

        row = QHBoxLayout()
        row.setSpacing(14)
        phone_card, pl = card_frame(margins=(8, 10, 8, 10), spacing=4)
        phone_card.setMinimumWidth(290)
        phone_card.setMaximumWidth(430)
        self.image = DeviceImage()
        self.name_lbl = StrongBodyLabel("")
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pills = QHBoxLayout()
        self.pill_mode = Pill("", "muted")
        self.pill_ios = Pill("", "muted")
        self.pills.addStretch(1)
        self.pills.addWidget(self.pill_mode)
        self.pills.addWidget(self.pill_ios)
        self.pills.addStretch(1)
        pl.addWidget(self.image, 1)
        self.photo_note = CaptionLabel("")
        i18n.bind(self.photo_note, "setText",
                  "Imagen ilustrativa: es la del modelo tal como salió al mercado, no la de tu dispositivo.",
                  "Illustrative image: the model as originally released, not your actual device.")
        self.photo_note.setWordWrap(True)
        self.photo_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo_note.setStyleSheet(f"color:{theme.MUTED}; font-size:11px")
        self.photo_note.setVisible(False)
        pl.addWidget(self.photo_note)
        pl.addWidget(self.name_lbl)
        pl.addLayout(self.pills)
        pl.addSpacing(2)
        pl.addWidget(self.b_fw)
        row.addWidget(phone_card, 5)

        info_card, il = card_frame(margins=(14, 12, 14, 12), spacing=8)
        self.search = SearchLineEdit()
        i18n.bind(self.search, "setPlaceholderText", "Buscar: serie, IMEI, batería…", "Search: serial, IMEI, battery…")
        self.search.textChanged.connect(self._filter)
        self.table = TableWidget()
        self.table.setColumnCount(2)
        self.table.setBorderVisible(False)
        self.table.horizontalHeader().setVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        privacy.connect_clicks(self.table, self._visible_rows, self._reveal, lambda: self._fill_table())
        privacy.bus.changed.connect(self._privacy_changed)
        self.empty = CaptionLabel("")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet(f"color:{theme.MUTED}")
        self.empty_logo = QLabel()
        self.empty_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if assets.exists("banner.png"):
            self.empty_logo.setPixmap(assets.banner_pixmap(210, opacity=0.5))
        self.empty_box = QWidget()
        eb = QVBoxLayout(self.empty_box)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(10)
        eb.addStretch(1)
        eb.addWidget(self.empty_logo)
        eb.addWidget(self.empty)
        eb.addStretch(1)
        il.addWidget(self.search)
        il.addWidget(self.table, 1)
        il.addWidget(self.empty_box, 1)
        row.addWidget(info_card, 6)
        self.body.addLayout(row, 1)

        monitor.changed.connect(self.on_state)
        i18n.on_change(lambda _c: self.on_state(self.state))
        self.on_state(monitor.state)

    def showEvent(self, event):
        super().showEvent(event)
        self._live_timer.start()
        self._live_poll()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._live_timer.stop()

    def _live_poll(self):
        udid = self.state.get("udid")
        if self.state.get("mode") != "normal" or not udid or not self.state.get("info") or self._live_busy \
                or not self.isVisible():
            return
        self._live_busy = True
        self._live_tick_count += 1
        include_disk = self._live is None or self._live_tick_count % 5 == 0
        previous_disk = (self._live or {}).get("disk")

        def work():
            return live_stats.live_stats(udid, include_disk)

        def ok(stats):
            self._live_busy = False
            if self.state.get("udid") != udid:
                return
            if not include_disk:
                stats["disk"] = previous_disk
            self._live = stats
            self._render_strip()

        def fail(_e):
            self._live_busy = False

        run_async(work, ok, fail)

    def _render_strip(self):
        battery, temp, storage, health = self.strip.tiles
        stats = self._live
        if self.state.get("mode") != "normal" or not stats:
            self.strip.clear()
            return
        level = stats["level"]
        if level is not None:
            if stats["full"]:
                status = tr("Carga completa", "Fully charged")
            elif stats["charging"]:
                status = tr("Cargando", "Charging")
            else:
                status = tr("Con cargador", "On charger") if stats["connected"] else tr("Descargando", "Discharging")
            tone = "ok" if stats["connected"] else "bad" if level <= 10 else "warn" if level <= 20 else "ok"
            battery.set(f"{level} %", level, status, tone)
        else:
            battery.clear()
        if stats["temperature"] is not None:
            value = stats["temperature"]
            temp.set(f"{value:.1f} °C", None, tr("Batería", "Battery"),
                     "bad" if value >= 45 else "warn" if value >= 40 else "ok")
        else:
            temp.clear(tr("No disponible en este iOS", "Not available on this iOS"))
        if stats["disk"]:
            total, free = stats["disk"]
            used_pct = (total - free) * 100 / total
            storage.set(fmt_bytes(free), used_pct,
                        tr(f"{fmt_bytes(total - free)} de {fmt_bytes(total)} en uso",
                           f"{fmt_bytes(total - free)} of {fmt_bytes(total)} used"),
                        "bad" if used_pct >= 95 else "warn" if used_pct >= 90 else "ok")
        else:
            storage.clear()
        if stats["health"] is not None:
            pct = stats["health"]
            cycles = tr(f"{stats['cycles']} ciclos de carga", f"{stats['cycles']} charge cycles") \
                if stats["cycles"] is not None else ""
            health.set(f"{pct:.0f} %", pct, cycles, "bad" if pct < 70 else "warn" if pct < 80 else "ok")
        else:
            health.clear(tr("No disponible en este iOS", "Not available on this iOS"))

    def _act(self, icon, es, en, fn):
        a = Action(icon, tr(es, en))
        a.triggered.connect(lambda *_: fn())
        self.bar.addAction(a)
        a._es_en = (es, en)
        i18n.on_change(lambda _c, a=a: a.setText(tr(*a._es_en)))
        return a

    def product(self):
        s = self.state
        if s["mode"] == "normal" and s.get("info"):
            return s["info"].get("ProductType", "")
        if s["mode"] == "recovery":
            return s.get("product", "")
        return ""

    def on_state(self, s):
        self.state = s
        if s.get("mode") != "normal" or s.get("udid") != self._live_udid:
            self._live = None
        self._live_udid = s.get("udid")
        mode, issue = s["mode"], s.get("issue")
        info = s.get("info") or {}
        rows = []
        if mode == "normal" and info:
            name = privacy.generic_name(info.get("DeviceName", tr("Dispositivo", "Device")), tr("iPhone / iPad", "iPhone / iPad"))
            self.title.setText(name)
            sub = tr("Conectado en modo normal.", "Connected in normal mode.")
            if s.get("count", 1) > 1:
                sub += tr(f'  ({s["count"]} dispositivos conectados, se usa el primero)',
                          f'  ({s["count"]} devices connected, using the first one)')
            self.subtitle.setText(sub)
            rows = [(f.label, f.value) for f in infomap.flatten(info, s.get("extra"))
                    if f.category != "other" or f.key in ("TimeZone",)]
            self.name_lbl.setText(name)
            self.pill_mode.setText(tr("Conectado", "Connected"))
            self.pill_mode.set_kind("ok")
            self.pill_ios.setText(f'iOS {info.get("ProductVersion", "?")}')
            self.pill_ios.set_kind("muted")
            self.pill_ios.show()
        elif mode == "normal":
            self.title.setText(tr("Dispositivo detectado", "Device detected"))
            self.subtitle.setText(tr("Falta establecer la confianza con el dispositivo.",
                                     "Trust this computer on the device to continue."))
            self.name_lbl.setText("iPhone / iPad")
            self.pill_mode.setText(tr("Sin confiar", "Not trusted"))
            self.pill_mode.set_kind("warn")
            self.pill_ios.hide()
        elif mode == "recovery":
            r = s["recovery"]
            self.title.setText(tr(f'Modo {r.get("MODE", "Recovery/DFU")}', f'{r.get("MODE", "Recovery/DFU")} mode'))
            self.subtitle.setText(tr("Dispositivo en Recovery/DFU. Listo para restaurar desde Flasheo.",
                                     "Device in Recovery/DFU. Ready to restore from Flash."))
            rows = [(f.label, f.value) for f in infomap.from_recovery(r)]
            self.name_lbl.setText(s.get("product", "") or "iPhone / iPad")
            self.pill_mode.setText(r.get("MODE", "Recovery/DFU"))
            self.pill_mode.set_kind("warn")
            self.pill_ios.hide()
        else:
            self.title.setText(tr("Sin dispositivo", "No device"))
            self.subtitle.setText(tr("Conecta un iPhone/iPad por USB y desbloquéalo.",
                                     "Connect and unlock an iPhone or iPad over USB."))
            self.name_lbl.setText(tr("Esperando dispositivo…", "Waiting for a device…"))
            self.pill_mode.setText(tr("Desconectado", "Disconnected"))
            self.pill_mode.set_kind("muted")
            self.pill_ios.hide()

        self.image.set_connected(mode in ("normal", "recovery"), mode)
        self._update_image(self.product())
        self._rows = rows
        self._fill_table()
        self._render_strip()
        self._live_poll()
        ok = mode == "normal" and bool(info)
        for a in (self.a_restart, self.a_shutdown, self.a_parts):
            a.setEnabled(ok)
        in_rec = mode == "recovery"
        self.a_recovery._es_en = ("Salir de Recovery", "Exit Recovery") if in_rec else ("Entrar en Recovery", "Enter Recovery")
        self.a_recovery.setText(tr(*self.a_recovery._es_en))
        self.a_recovery.setIcon(FIF.RETURN if in_rec else FIF.DEVELOPER_TOOLS)
        self.a_recovery.setEnabled(ok or in_rec)
        self.a_pdf.setEnabled(ok or mode == "recovery")
        self.b_fw.setEnabled(bool(self.product()))
        self._assistant(issue, s)

    def _visible_rows(self):
        t = self.search.text().strip().lower()
        return [r for r in self._rows if not t or t in privacy.searchable(r[0], r[1]).lower()]

    def _privacy_changed(self):
        self._reveal.reset()
        self.on_state(self.state)

    def _fill_table(self):
        rows = self._visible_rows()
        privacy.fill_table(self.table, rows, self._reveal)
        self.table.setVisible(bool(rows))
        self.empty_box.setVisible(not rows)
        self.empty_logo.setVisible(not self._rows)
        self.empty.setText(tr("Aquí aparecerán los datos del dispositivo.", "Device details will appear here.")
                           if not self._rows else tr("Nada coincide con la búsqueda.", "No matches."))

    def _filter(self, _text):
        self._fill_table()

    def _show_component_details(self):
        info = self.state.get("info") or {}
        extra = self.state.get("extra") or {}
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Detalles del dispositivo / componentes", "Device / component details"))
        dlg.resize(640, 460)
        lay = QVBoxLayout(dlg)
        note = QLabel(tr("Solo se muestran identificadores que iOS expone por software. Que un número no aparezca "
                         "no demuestra que la pieza se haya cambiado.",
                         "Only identifiers exposed by iOS are shown. A missing number does not prove a part was replaced."))
        note.setWordWrap(True)
        lay.addWidget(note)
        table = TableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels([tr("Componente / campo", "Component / field"), tr("Valor", "Value")])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().hide()
        reveal = privacy.Reveal()
        fields = [
            (tr("Modelo", "Model"), info.get("ProductType")),
            (tr("Número de serie del dispositivo", "Device serial number"), info.get("SerialNumber")),
            (tr("Número de serie de placa lógica (MLB)", "Logic board serial (MLB)"), info.get("MLBSerialNumber")),
            (tr("Número de serie de banda base", "Baseband serial"), info.get("BasebandSerialNumber")),
            ("IMEI", info.get("InternationalMobileEquipmentIdentity")),
            ("ECID / Chip ID", info.get("UniqueChipID")),
            (tr("Dirección Wi-Fi", "Wi-Fi address"), info.get("WiFiAddress")),
            (tr("Dirección Bluetooth", "Bluetooth address"), info.get("BluetoothAddress")),
        ]
        for key, value in extra.items():
            if any(w in str(key).lower() for w in ("serial", "battery", "camera", "part", "cycle", "capacity")) \
                    and not isinstance(value, (dict, list, tuple)):
                fields.append((str(key), value))
        rows = [(str(k), str(v)) for k, v in fields if v not in (None, "", "N/A")]
        privacy.fill_table(table, rows, reveal)
        privacy.connect_clicks(table, lambda: rows, reveal, lambda: privacy.fill_table(table, rows, reveal))
        lay.addWidget(table, 1)
        dlg.exec()

    def _update_image(self, ident):
        if ident == self._img_ident:
            return
        self._img_ident = ident
        self.image.set_pixmap(None)
        self.photo_note.setVisible(False)
        if not ident:
            return

        def work():
            url = catalog.device_image_url(ident)
            return catalog.download_image(url) if url else None

        def ok(path):
            if ident != self._img_ident or not path:
                return
            pm = QPixmap(path)
            if not pm.isNull():
                self.image.set_pixmap(pm)
                self.photo_note.setVisible(True)

        def fail(_e):
            if ident == self._img_ident:
                self._img_ident = None

        run_async(work, ok, fail)

    def set_language(self, language):
        pass

    def _assistant(self, issue, s):
        self._fix_issue = issue
        ipheth = s.get("ipheth") or connection.ipheth_loaded()
        msgs = {
            "pending": (tr("<b>Mira la pantalla del iPhone y pulsa «Confiar»</b> (te pedirá el código). Si no ha salido el aviso, reenvíalo.",
                           "<b>Look at the iPhone screen and tap “Trust”</b> (it will ask for your passcode). If nothing appeared, resend the prompt."),
                        tr("Reenviar aviso", "Resend prompt"), None, FIF.PHONE),
            "denied": (tr("Pulsaste «No confiar». Reenvía el aviso y esta vez pulsa «Confiar». Si no vuelve a preguntar: Ajustes → General → Transferir o restablecer → Restablecer ubicación y privacidad.",
                          "You tapped “Don’t Trust”. Resend the prompt and tap “Trust”. If it won’t ask again: Settings → General → Transfer or Reset → Reset Location & Privacy."),
                       tr("Reenviar aviso", "Resend prompt"), None, FIF.CANCEL),
            "passcode": (tr("El iPhone tiene código: <b>desbloquéalo</b> y vuelve a conectar el cable.",
                            "The iPhone is locked: <b>unlock it</b> and reconnect the cable."),
                         tr("Reintentar", "Retry"), None, FIF.CERTIFICATE),
            "mux": (tr("Veo el dispositivo por USB pero el ordenador no puede comunicarse con él. ", "The device is visible over USB but this computer can’t talk to it. ")
                    + (tr("El módulo <b>ipheth</b> (internet por USB) lo tiene acaparado. ", "The <b>ipheth</b> module (USB tethering) has claimed it. ")
                       if ipheth else tr("Prueba otro cable de datos o un puerto USB 2.0. ", "Try another data cable or a USB 2.0 port. "))
                    + tr("Pulsa Reparar y luego <b>desconecta y vuelve a conectar</b> el cable.",
                         "Press Repair, then <b>unplug and replug</b> the cable."),
                    tr("Reparar conexión…", "Repair connection…"), None, FIF.CONNECT),
            "ssl": (tr("Hay un emparejado antiguo o corrupto (error TLS). Se borra y se vuelve a pedir confiar.",
                       "An old or corrupt pairing record exists (TLS error). It will be cleared and trust requested again."),
                    tr("Borrar emparejados", "Clear pairings"), None, FIF.CERTIFICATE),
            "hostid": (tr("El emparejado guardado no es válido. Se borra y se vuelve a pedir confiar.",
                          "The saved pairing is invalid. It will be cleared and trust requested again."),
                       tr("Borrar emparejados", "Clear pairings"), None, FIF.CERTIFICATE),
            "repairing": (tr("Hay un problema de conexión. <b>Borrando los emparejados guardados</b> en segundo plano… "
                             "(si sale la ventana de contraseña, escríbela)",
                             "Connection problem. <b>Clearing the saved pairings</b> in the background… "
                             "(enter your password if prompted)"),
                          None, None, FIF.SYNC),
            "usbmuxd_down": (tr("El servicio <b>usbmuxd</b> no responde.", "The <b>usbmuxd</b> service is not responding."),
                             tr("Reiniciar usbmuxd", "Restart usbmuxd"), None, FIF.SYNC),
            "no_usb": (tr("No veo ningún iPhone/iPad por USB. Usa un cable <b>de datos</b> (no solo de carga) y prueba otro puerto.",
                          "No iPhone/iPad seen over USB. Use a <b>data</b> cable (not charge-only) and try another port."),
                       None, None, FIF.SEARCH),
            "tools": (s.get("error", tr("Faltan herramientas.", "Missing tools.")), None, None, FIF.DEVELOPER_TOOLS),
            "error": (s.get("error", tr("Error desconocido", "Unknown error")),
                      tr("Borrar emparejados", "Clear pairings"), None, FIF.INFO),
        }
        if not issue or issue not in msgs:
            self.banner.setVisible(False)
            return
        text, b1, b2, icon = msgs[issue]
        self.banner.show_message(text, b1, b2, icon)

    def _fix_action(self, _which):
        issue = self._fix_issue
        if issue in ("pending", "denied"):
            self.banner.msg.setText(tr("Aviso reenviado: mira el iPhone y pulsa «Confiar».",
                                       "Prompt resent: check the iPhone and tap “Trust”."))
            self.monitor.request_pair()
        elif issue == "passcode":
            self.monitor.refresh()
        elif issue == "mux":
            self._fix_ipheth()
        elif issue in ("ssl", "hostid", "error"):
            self._run_fix("reset_pairing", tr("Emparejado borrado. Desconecta y vuelve a conectar el cable.",
                                              "Pairing cleared. Unplug and replug the cable."))
        elif issue == "usbmuxd_down":
            self._run_fix("start_usbmuxd", tr("usbmuxd reiniciado.", "usbmuxd restarted."))

    def _fix_ipheth(self):
        m = QMessageBox(self)
        m.setWindowTitle(tr("Reparar conexión", "Repair connection"))
        m.setIcon(QMessageBox.Icon.Question)
        m.setText(tr("Descargar el módulo <b>ipheth</b> del kernel para que el ordenador pueda comunicarse con el iPhone.",
                     "Unload the <b>ipheth</b> kernel module so this computer can talk to the iPhone."))
        m.setInformativeText(tr(
            "• <b>Bloquear</b>: queda arreglado siempre. Contra: el iPhone no dará internet por USB. Se deshace desde Herramientas.<br>"
            "• <b>Solo esta vez</b>: se descarga ahora, pero puede volver al reconectar.<br><br>Pedirá la contraseña de administrador.",
            "• <b>Block</b>: fixed permanently. Downside: no USB tethering. Undo from Tools.<br>"
            "• <b>Just this time</b>: unloaded now, may come back on reconnect.<br><br>Administrator password required."))
        b_block = m.addButton(tr("Bloquear ipheth (recomendado)", "Block ipheth (recommended)"), QMessageBox.ButtonRole.AcceptRole)
        b_once = m.addButton(tr("Solo esta vez", "Just this time"), QMessageBox.ButtonRole.ActionRole)
        m.addButton(tr("Cancelar", "Cancel"), QMessageBox.ButtonRole.RejectRole)
        m.exec()
        done = tr("Listo. Ahora desconecta y vuelve a conectar el cable.", "Done. Now unplug and replug the cable.")
        if m.clickedButton() is b_block:
            self._run_fix("ipheth_block", done)
        elif m.clickedButton() is b_once:
            self._run_fix("ipheth_once", done)

    def _run_fix(self, name, ok_msg):
        self.banner.msg.setText(tr("Aplicando reparación… (si sale la ventana de contraseña, escríbela)",
                                   "Applying fix… (enter your password if prompted)"))

        def done(res):
            rc, out, err = res
            if rc == 0:
                toast(self, "ok", tr("Reparación aplicada", "Fix applied"), ok_msg)
                self.monitor.refresh()
            else:
                txt = (out + err).decode(errors="replace").strip()
                toast(self, "err", tr("No se pudo aplicar", "Could not apply"), f"({rc}) {txt}", 8000)

        run_async(lambda: tools.run(connection.fix_cmd(name), timeout=180), done,
                  lambda e: toast(self, "err", "Error", str(e), 8000))

    def _toggle_recovery(self):
        if self.state.get("mode") == "recovery":
            self._cmd(["irecovery", "-n"], tr("Saliendo de Recovery…", "Leaving Recovery…"))
        else:
            self._enter_recovery()

    def _enter_recovery(self):
        udid = self.state.get("udid")
        if not udid:
            return
        if QMessageBox.question(self, "Recovery", tr("¿Poner el dispositivo en modo Recovery?",
                                                    "Put the device into Recovery mode?")) != QMessageBox.StandardButton.Yes:
            return
        self._cmd(["ideviceenterrecovery", udid], tr("Entrando en Recovery…", "Entering Recovery…"))

    def _cmd(self, args, msg):
        toast(self, "info", msg, "", 2500)

        def work():
            rc, out, err = tools.run(args, timeout=30)
            return rc, (out + err).decode(errors="replace").strip()

        def done(res):
            rc, txt = res
            if rc == 0:
                toast(self, "ok", tr("Hecho", "Done"), txt, 3000)
            else:
                toast(self, "err", f"Error ({rc})", txt, 7000)
            self.monitor.poll()

        run_async(work, done, lambda e: toast(self, "err", "Error", str(e), 7000))

import base64
from pathlib import Path

from PySide6.QtCore import QMarginsF, QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPageLayout, QPageSize, QPdfWriter, QPixmap, QTextDocument
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QTableWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (Action, CaptionLabel, CommandBar, FluentIcon as FIF, PrimaryPushButton, RoundMenu,
                            SearchLineEdit, StrongBodyLabel, TableWidget)

from .. import assets, i18n, privacy, theme
from ..core import android, android_catalog
from ..core.util import fmt_bytes
from ..dispatch import run_async
from ..i18n import tr
from .android_base import (AndroidMonitor, AndroidPage, confirm, relayout_bar,
                           set_action_text, short_error)
from .android_device_image import AndroidDeviceImage
from .components import Pill, card_frame, toast
from .stat_strip import StatStrip

INFO_FIELDS = (
    ("Fabricante", "Manufacturer", "ro.product.manufacturer"),
    ("Marca", "Brand", "ro.product.brand"),
    ("Modelo", "Model", "ro.product.model"),
    ("Nombre del producto", "Product name", "ro.product.name"),
    ("Código del dispositivo", "Device codename", "ro.product.device"),
    ("Versión de Android", "Android version", "ro.build.version.release"),
    ("Nivel de API", "API level", "ro.build.version.sdk"),
    ("Parche de seguridad", "Security patch", "ro.build.version.security_patch"),
    ("Número de compilación", "Build number", "ro.build.display.id"),
    ("Versión incremental", "Incremental build", "ro.build.version.incremental"),
    ("Tipo de compilación", "Build type", "ro.build.type"),
    ("Fecha de compilación", "Build date", "ro.build.date"),
    ("Huella de compilación", "Build fingerprint", "ro.build.fingerprint"),
    ("Procesador (ABI)", "Processor (ABI)", "ro.product.cpu.abi"),
    ("Hardware", "Hardware", "ro.hardware"),
    ("Placa", "Board", "ro.product.board"),
    ("Bootloader", "Bootloader", "ro.bootloader"),
    ("Bootloader bloqueado", "Bootloader locked", "ro.boot.flash.locked"),
    ("Estado de arranque verificado", "Verified boot state", "ro.boot.verifiedbootstate"),
    ("Cifrado", "Encryption", "ro.crypto.state"),
    ("Project Treble", "Project Treble", "ro.treble.enabled"),
    ("Banda base", "Baseband", "gsm.version.baseband"),
    ("Operador", "Operator", "gsm.operator.alpha"),
    ("Estado de la SIM", "SIM state", "gsm.sim.state"),
    ("Idioma", "Language", "persist.sys.locale"),
    ("Zona horaria", "Time zone", "persist.sys.timezone"),
)
COMPONENT_FIELDS = (
    ("Fabricante", "Manufacturer", "ro.product.manufacturer"), ("Modelo", "Model", "ro.product.model"),
    ("Número de serie", "Serial number", "ro.serialno"), ("Hardware", "Hardware", "ro.hardware"),
    ("Placa", "Board", "ro.product.board"), ("Plataforma", "Platform", "ro.board.platform"),
    ("Procesador (ABI)", "Processor (ABI)", "ro.product.cpu.abi"), ("Banda base", "Baseband", "gsm.version.baseband"),
    ("Bootloader", "Bootloader", "ro.bootloader"), ("Operador", "Operator", "gsm.operator.alpha"),
    ("Estado de la SIM", "SIM state", "gsm.sim.state"),
)


def fmt_duration(seconds):
    seconds = int(seconds or 0)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    parts = ([f"{days} d"] if days else []) + ([f"{hours} h"] if hours or days else []) + [f"{rest // 60} min"]
    return " ".join(parts)


def stats_rows(overview):
    rows = []
    battery = overview["battery"]
    if battery["level"] is not None:
        bits = [f"{battery['level']} %"]
        status = android.BATTERY_STATUS.get(battery["status"])
        health = android.BATTERY_HEALTH.get(battery["health"])
        if status:
            bits.append(tr(*status))
        if battery["temperature"] is not None:
            bits.append(f"{battery['temperature']:.1f} °C")
        if health:
            bits.append(tr(*health))
        rows.append((tr("Batería", "Battery"), " · ".join(bits)))
        if battery["technology"]:
            rows.append((tr("Tecnología de batería", "Battery technology"), battery["technology"]))
        if battery["voltage"]:
            rows.append((tr("Voltaje de batería", "Battery voltage"), f"{battery['voltage']} mV"))
    for key, es, en in (("storage", "Almacenamiento", "Storage"), ("memory", "Memoria RAM", "RAM")):
        if overview[key]:
            total, used = overview[key]
            percent = used * 100 / total if total else 0
            rows.append((tr(es, en), tr(f"{fmt_bytes(used)} de {fmt_bytes(total)} ({percent:.0f} % en uso)",
                                        f"{fmt_bytes(used)} of {fmt_bytes(total)} ({percent:.0f}% used)")))
    if overview["screen"]:
        dpi = f" · {overview['density']} dpi" if overview["density"] else ""
        rows.append((tr("Pantalla", "Screen"), overview["screen"] + dpi))
    if overview["ip"]:
        rows.append((tr("IP de Wi-Fi", "Wi-Fi IP"), overview["ip"]))
    if overview["uptime"]:
        rows.append((tr("Tiempo encendido", "Uptime"), fmt_duration(overview["uptime"])))
    return rows


class AndroidTab(AndroidPage):

    goto_apps = Signal()

    def __init__(self, monitor, parent=None):
        super().__init__("android", ("Sin dispositivo", "No device"), ("", ""), monitor, fastboot_ok=True,
                         parent=parent)
        self._properties = {}
        self._overview = None
        self._fastboot_rows = []
        self._identity = None
        self._img_key = None
        self._rows = []
        self._reveal = privacy.Reveal()
        self._loading = False

        self.strip = StatStrip([("Batería", "Battery"), ("Temperatura", "Temperature"),
                                ("Almacenamiento libre", "Free storage"), ("Memoria RAM en uso", "RAM in use")])
        self.body.addWidget(self.strip)

        self.bar = CommandBar()
        self.bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.a_refresh = self._act(FIF.SYNC, "Actualizar", "Refresh", self.reload)
        self.bar.addSeparator()
        self.a_restart = self._act(FIF.ROTATE, "Reiniciar", "Restart", self._restart)
        self.a_shutdown = self._act(FIF.POWER_BUTTON, "Apagar", "Shut down", self._shutdown)
        self.bar.addSeparator()
        self.a_recovery = self._act(FIF.DEVELOPER_TOOLS, "Entrar en Recovery", "Enter Recovery", self._toggle_recovery)
        self.a_bootloader = self._act(FIF.CODE, "Entrar en Bootloader", "Enter Bootloader", self._enter_bootloader)
        self.bar.addSeparator()
        self.a_parts = self._act(FIF.TAG, "Componentes", "Components", self._show_component_details)
        self.a_pdf = self._act(FIF.DOCUMENT, "Informe PDF", "PDF report", self._report_pdf)
        self.b_apps = PrimaryPushButton(FIF.APPLICATION, "")
        i18n.bind(self.b_apps, "setText", "Ver aplicaciones", "Browse apps")
        self.b_apps.clicked.connect(self.goto_apps.emit)
        self.body.addWidget(self.bar)

        row = QHBoxLayout()
        row.setSpacing(14)
        phone_card, pl = card_frame(margins=(8, 10, 8, 10), spacing=4)
        phone_card.setMinimumWidth(290)
        phone_card.setMaximumWidth(430)
        self.image = AndroidDeviceImage()
        self.name_lbl = StrongBodyLabel("")
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_lbl.setWordWrap(True)
        self.pills = QHBoxLayout()
        self.pill_mode = Pill("", "muted")
        self.pill_ver = Pill("", "muted")
        self.pills.addStretch(1)
        self.pills.addWidget(self.pill_mode)
        self.pills.addWidget(self.pill_ver)
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
        pl.addWidget(self.b_apps)
        row.addWidget(phone_card, 5)

        info_card, il = card_frame(margins=(14, 12, 14, 12), spacing=8)
        self.search = SearchLineEdit()
        i18n.bind(self.search, "setPlaceholderText", "Buscar: serie, Android, batería…",
                  "Search: serial, Android, battery…")
        self.search.textChanged.connect(lambda _t: self._fill_table())
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
        self.table.setWordWrap(True)
        self.table.verticalHeader().setMinimumSectionSize(34)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        privacy.connect_clicks(self.table, self._visible_rows, self._reveal, lambda: self._fill_table())
        privacy.bus.changed.connect(self._privacy_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._row_menu)
        self.table.cellDoubleClicked.connect(lambda r, _c: self._copy_value(r))
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
        hint = CaptionLabel("")
        i18n.bind(hint, "setText", "Doble clic para copiar un valor · clic derecho para más opciones",
                  "Double-click to copy a value · right-click for more options")
        hint.setStyleSheet(f"color:{theme.MUTED}")
        il.addWidget(self.search)
        il.addWidget(self.table, 1)
        il.addWidget(self.empty_box, 1)
        il.addWidget(hint)
        row.addWidget(info_card, 6)
        self.body.addLayout(row, 1)

        self._ov_busy = False
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._refresh_overview)
        i18n.on_change(lambda _c: self._render())
        self.finish_setup()

    def _act(self, icon, es, en, fn):
        action = Action(icon, tr(es, en))
        action.triggered.connect(lambda *_: fn())
        self.bar.addAction(action)
        action._es_en = (es, en)
        i18n.on_change(lambda _c, a=action: a.setText(tr(*a._es_en)))
        return action

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def on_device_changed(self):
        self._properties = {}
        self._overview = None
        self._fastboot_rows = []
        self._identity = None
        self._img_key = None
        self._loading = False
        self._ov_busy = False
        self.image.set_pixmap(None)
        self.photo_note.setVisible(False)
        self._render()

    def update_actions(self):
        self._render_buttons()

    def reload(self):
        self._img_key = None
        super().reload()

    def load(self):
        device = self.device
        if not device:
            return
        serial = device["serial"]
        self._loading = True
        self._render()
        if device["status"] == "fastboot":
            run_async(lambda: android.fastboot_info(serial), self.guard(self._fastboot_loaded), self.guard(self._failed))
            return
        run_async(lambda: android.get_properties(serial), self.guard(self._props_loaded), self.guard(self._failed))
        self._refresh_overview()

    def _refresh_overview(self):
        device = self.device
        if not device or device["status"] != "device" or not self.isVisible():
            return
        if self._ov_busy:
            return
        self._ov_busy = True
        serial = device["serial"]
        done = self.guard(self._overview_loaded)

        def finished(overview):
            self._ov_busy = False
            done(overview)

        run_async(lambda: android.get_overview(serial), finished, lambda _e: setattr(self, "_ov_busy", False))

    def _props_loaded(self, properties):
        self._loading = False
        self._properties = properties
        self._render()
        self._update_image(properties)

    def _fastboot_loaded(self, rows):
        self._loading = False
        self._fastboot_rows = rows
        self._render()

    def _overview_loaded(self, overview):
        self._overview = overview
        self._render()

    def _failed(self, error):
        self._loading = False
        toast(self, "err", tr("No se pudo leer el dispositivo", "Could not read the device"), short_error(error), 7000)
        self._render()

    def _update_image(self, props):
        key = f"{props.get('ro.product.model', '')}|{props.get('ro.product.device', '')}"
        if key == self._img_key or not props:
            return
        self._img_key = key
        generation = self._gen

        def ok(result):
            if generation != self._gen:
                return
            self._identity = result
            self._render()
            if result.get("image"):
                pixmap = QPixmap(result["image"])
                if not pixmap.isNull():
                    self.image.set_pixmap(pixmap)
                    self.photo_note.setVisible(True)

        def fail(_error):
            if generation == self._gen:
                self._img_key = None

        run_async(lambda: android_catalog.identify(props), ok, fail)

    def _model_name(self):
        props = self._properties
        if self._identity and self._identity.get("name"):
            return self._identity["name"]
        return android_catalog.display_name(props, None) if props else ""

    def _render(self):
        device = self.device
        fastboot = bool(device and device["status"] == "fastboot")
        connected = bool(device and device["status"] in ("device", "fastboot"))
        if device and device["status"] == "device":
            name = self._model_name() or device["model"].replace("_", " ") or tr("Dispositivo", "Device")
            self.title.setText(name)
            self.subtitle.setText(tr("Conectado en modo normal.", "Connected in normal mode."))
            self.name_lbl.setText(name)
            self.pill_mode.setText(tr("Conectado", "Connected"))
            self.pill_mode.set_kind("ok")
            version = self._properties.get("ro.build.version.release", "")
            self.pill_ver.setText(f"Android {version}" if version else "Android")
            self.pill_ver.set_kind("muted")
            self.pill_ver.show()
        elif fastboot:
            self.title.setText(tr("Modo Fastboot", "Fastboot mode"))
            self.subtitle.setText(tr("Dispositivo en Fastboot. Datos de solo lectura del bootloader.",
                                     "Device in Fastboot. Read-only bootloader information."))
            self.name_lbl.setText(privacy.generic_name(device["serial"], "Fastboot"))
            self.pill_mode.setText("Fastboot")
            self.pill_mode.set_kind("warn")
            self.pill_ver.hide()
        elif device:
            self.title.setText(tr("Dispositivo detectado", "Device detected"))
            self.subtitle.setText(tr("Falta autorizar este equipo en el móvil.", "Authorize this computer on the phone."))
            self.name_lbl.setText(android.device_label(device) or "Android")
            self.pill_mode.setText(tr("Sin autorizar", "Unauthorized") if device["status"] == "unauthorized"
                                   else device["status"])
            self.pill_mode.set_kind("warn")
            self.pill_ver.hide()
        else:
            self.title.setText(tr("Sin dispositivo", "No device"))
            self.subtitle.setText(tr("Conecta un Android por USB y activa la depuración USB.",
                                     "Connect an Android over USB and turn on USB debugging."))
            self.name_lbl.setText(tr("Esperando dispositivo…", "Waiting for a device…"))
            self.pill_mode.setText(tr("Desconectado", "Disconnected"))
            self.pill_mode.set_kind("muted")
            self.pill_ver.hide()
        self.image.set_connected(connected, "normal" if device and device["status"] == "device" else "recovery")
        self.strip.setVisible(not fastboot)
        self._render_strip()
        self._build_rows()
        self._fill_table()
        self._render_buttons()

    def _render_strip(self):
        battery_tile, temp_tile, storage_tile, ram_tile = self.strip.tiles
        overview = self._overview
        if not overview or not (self.device and self.device["status"] == "device"):
            self.strip.clear()
            return
        battery = overview["battery"]
        if battery["level"] is not None:
            status = android.BATTERY_STATUS.get(battery["status"])
            level = "ok"
            if not battery["plugged"]:
                level = "bad" if battery["level"] <= 10 else "warn" if battery["level"] <= 20 else "ok"
            battery_tile.set(f"{battery['level']} %", battery["level"], tr(*status) if status else "", level)
        else:
            battery_tile.clear()
        temperature = battery["temperature"]
        if temperature is not None:
            cpu = overview.get("cpu_temp")
            detail = tr("Batería", "Battery") + (f" · CPU {cpu:.0f} °C" if cpu else "")
            temp_tile.set(f"{temperature:.1f} °C", None, detail,
                          "bad" if temperature >= 45 else "warn" if temperature >= 40 else "ok")
        else:
            temp_tile.clear(tr("No disponible", "Not available"))
        for tile, key in ((storage_tile, "storage"), (ram_tile, "memory")):
            if not overview[key]:
                tile.clear()
                continue
            total, used = overview[key]
            percent = used * 100 / total if total else 0
            level = "bad" if percent >= 95 else "warn" if percent >= 90 else "ok"
            if key == "storage":
                tile.set(fmt_bytes(total - used), percent,
                         tr(f"{fmt_bytes(used)} de {fmt_bytes(total)} en uso", f"{fmt_bytes(used)} of {fmt_bytes(total)} used"),
                         level)
            else:
                tile.set(fmt_bytes(used), percent, tr(f"de {fmt_bytes(total)} ({percent:.0f} %)", f"of {fmt_bytes(total)} ({percent:.0f}%)"),
                         level)

    def _render_buttons(self):
        device = self.device
        fastboot = bool(device and device["status"] == "fastboot")
        normal = bool(device and device["status"] == "device")
        act = self.can_act()
        for action in (self.a_restart, self.a_shutdown, self.a_parts):
            action.setEnabled(act and normal)
        self.a_bootloader.setEnabled(act and normal)
        if set_action_text(self.a_recovery, *(("Salir de Fastboot", "Leave Fastboot") if fastboot
                                              else ("Entrar en Recovery", "Enter Recovery"))):
            relayout_bar(self.bar)
        self.a_recovery.setIcon(FIF.RETURN if fastboot else FIF.DEVELOPER_TOOLS)
        self.a_recovery.setEnabled(act and (normal or fastboot))
        self.a_pdf.setEnabled(bool(self._rows))
        self.a_refresh.setEnabled(not self.busy)
        self.b_apps.setEnabled(normal)

    def _build_rows(self):
        device = self.device
        rows = []
        if device and device["status"] == "device":
            props = self._properties
            rows = [(tr(es, en), props[key]) for es, en, key in INFO_FIELDS if props.get(key)]
            rows.insert(0, (tr("Número de serie", "Serial number"), device["serial"]))
            if self._identity and self._identity.get("name"):
                rows.insert(1, (tr("Nombre comercial", "Marketing name"), self._identity["name"]))
            if self._overview:
                rows += stats_rows(self._overview)
        elif device and device["status"] == "fastboot":
            rows = [(tr("Número de serie", "Serial number"), device["serial"])] + list(self._fastboot_rows)
        self._rows = rows

    def _visible_rows(self):
        query = self.search.text().strip().lower()
        return [r for r in self._rows if not query or query in privacy.searchable(r[0], r[1]).lower()]

    def _privacy_changed(self):
        self._reveal.reset()
        self._render()

    def _fill_table(self):
        rows = self._visible_rows()
        privacy.fill_table(self.table, rows, self._reveal)
        self.table.setVisible(bool(rows))
        self.empty_box.setVisible(not rows)
        self.empty_logo.setVisible(not self._rows)
        if self._loading and not self._rows:
            self.empty.setText(tr("Leyendo el dispositivo…", "Reading the device…"))
        elif not self._rows:
            self.empty.setText(tr("Aquí aparecerán los datos del dispositivo.", "Device details will appear here."))
        else:
            self.empty.setText(tr("Nada coincide con la búsqueda.", "No matches."))

    def _copy_value(self, row):
        rows = self._visible_rows()
        if 0 <= row < len(rows):
            value = privacy.clean_for_copy(rows[row][0], rows[row][1])
            if value is None:
                toast(self, "warn", tr("Contenido oculto", "Hidden content"), privacy.hint(), 3500)
                return
            QGuiApplication.clipboard().setText(value)
            toast(self, "ok", tr("Copiado", "Copied"), rows[row][0], 2000)

    def _row_menu(self, pos):
        row = self.table.rowAt(pos.y())
        rows = self._visible_rows()
        if not 0 <= row < len(rows):
            return
        label, value = rows[row]
        value = privacy.report_value(label, value)
        menu = RoundMenu(parent=self)
        menu.addAction(Action(FIF.COPY, tr("Copiar valor", "Copy value"),
                              triggered=lambda: QGuiApplication.clipboard().setText(value)))
        menu.addAction(Action(FIF.DOCUMENT, tr("Copiar fila", "Copy row"),
                              triggered=lambda: QGuiApplication.clipboard().setText(f"{label}: {value}")))
        menu.addAction(Action(FIF.SHARE, tr("Copiar todo", "Copy everything"), triggered=lambda: QGuiApplication
                              .clipboard().setText("\n".join(f"{k}: {privacy.report_value(k, v)}" for k, v in self._rows))))
        menu.exec(self.table.viewport().mapToGlobal(QPoint(pos.x(), pos.y())))

    def _show_component_details(self):
        props = self._properties
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Detalles del dispositivo / componentes", "Device / component details"))
        dialog.resize(640, 460)
        lay = QVBoxLayout(dialog)
        note = QLabel(tr("Solo se muestran identificadores que Android expone por software. Que un número no "
                         "aparezca no demuestra que la pieza se haya cambiado.",
                         "Only identifiers exposed by Android are shown. A missing number does not prove a part "
                         "was replaced."))
        note.setWordWrap(True)
        lay.addWidget(note)
        table = TableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels([tr("Componente / campo", "Component / field"), tr("Valor", "Value")])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().hide()
        rows = [(tr(es, en), props[key]) for es, en, key in COMPONENT_FIELDS if props.get(key)]
        reveal = privacy.Reveal()
        privacy.fill_table(table, rows, reveal)
        privacy.connect_clicks(table, lambda: rows, reveal, lambda: privacy.fill_table(table, rows, reveal))
        lay.addWidget(table, 1)
        dialog.exec()

    def report_html(self):
        def esc(text):
            return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        def image_tag(path, width):
            try:
                data = base64.b64encode(Path(path).read_bytes()).decode()
                return f'<img src="data:image/png;base64,{data}" width="{width}">'
            except OSError:
                return ""

        banner = image_tag(assets.path("banner.png"), 180) if assets.exists("banner.png") else ""
        phone = image_tag(self._identity["image"], 150) if self._identity and self._identity.get("image") else ""
        body = "".join(f"<tr><td style='padding:3px 10px 3px 0;color:#555'>{esc(k)}</td>"
                       f"<td>{esc(privacy.report_value(k, v))}</td></tr>" for k, v in self._rows)
        return (f"<html><body style='font-family:sans-serif;font-size:10pt'>{banner}"
                f"<h2>{esc(self.title.text())}</h2><p>{phone}</p><table>{body}</table>"
                f"<hr><p style='color:#888;font-size:8pt'>{esc(tr('Generado con VeyloraDevice · VeyloraLabs', 'Generated with VeyloraDevice · VeyloraLabs'))}</p>"
                "</body></html>")

    def write_report(self, path):
        document = QTextDocument()
        document.setHtml(self.report_html())
        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)
        document.print_(writer)

    def _report_pdf(self):
        if not self._rows:
            return
        serial = "android" if privacy.enabled() else (self.device or {}).get("serial", "android").replace(":", "_")
        path, _ = QFileDialog.getSaveFileName(self, tr("Guardar informe", "Save report"),
                                              str(Path.home() / f"informe-android-{serial}.pdf"), "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            self.write_report(path)
        except OSError as exc:
            toast(self, "err", tr("No se pudo guardar", "Could not save"), str(exc), 6000)
            return
        toast(self, "ok", tr("Informe guardado", "Report saved"), path, 4000)

    def _send(self, mode, message):
        device = self.device
        if not device or not self.can_act():
            return
        serial = device["serial"]
        toast(self, "info", message, "", 2500)

        def work():
            if device["status"] == "fastboot":
                android.fastboot_reboot(serial, mode)
            else:
                android.reboot(serial, mode)

        self.run_task(work, done=lambda _r: self.monitor.refresh(), ok_title=tr("Hecho", "Done"),
                      ok_text=tr("Orden enviada al dispositivo.", "Command sent to the device."))

    def _restart(self):
        self._send("system", tr("Reiniciando…", "Restarting…"))

    def _shutdown(self):
        if confirm(self, tr("Apagar", "Shut down"),
                   tr("El móvil se apagará. Para encenderlo tendrás que mantener pulsado el botón de encendido.",
                      "The phone will turn off. To turn it on you will have to hold the power button."),
                   ok=tr("Apagar", "Shut down"), danger=True):
            self._send("poweroff", tr("Apagando…", "Shutting down…"))

    def _toggle_recovery(self):
        device = self.device
        if device and device["status"] == "fastboot":
            self._send("system", tr("Saliendo de Fastboot…", "Leaving Fastboot…"))
        elif confirm(self, "Recovery", tr("¿Poner el dispositivo en modo Recovery?\n\nPara salir, elige «Reiniciar» "
                                          "en ese menú o mantén pulsado el botón de encendido.",
                                          "Put the device into Recovery mode?\n\nTo leave it, choose “Reboot” in "
                                          "that menu or hold the power button."),
                     ok=tr("Entrar en Recovery", "Enter Recovery")):
            self._send("recovery", tr("Entrando en Recovery…", "Entering Recovery…"))

    def _enter_bootloader(self):
        if confirm(self, "Bootloader", tr("¿Reiniciar en el bootloader (Fastboot)?\n\nNo se borra nada por hacerlo. "
                                          "Para salir usa «Salir de Fastboot» aquí.",
                                          "Reboot into the bootloader (Fastboot)?\n\nNothing is erased by doing "
                                          "this. To leave it use “Leave Fastboot” here."),
                   ok=tr("Entrar en Bootloader", "Enter Bootloader")):
            self._send("bootloader", tr("Entrando en el bootloader…", "Entering the bootloader…"))

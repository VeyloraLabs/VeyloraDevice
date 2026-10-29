
MODEL_BASE = {
    'iPhone10,1': ('iPhone 8', 45, 75), 'iPhone10,4': ('iPhone 8', 45, 75),
    'iPhone10,2': ('iPhone 8 Plus', 55, 90), 'iPhone10,5': ('iPhone 8 Plus', 55, 90),
    'iPhone12,8': ('iPhone SE (2020)', 55, 95),
    'iPhone14,6': ('iPhone SE (2022)', 90, 145),
    'iPhone11,8': ('iPhone XR', 80, 130), 'iPhone12,1': ('iPhone 11', 90, 150),
    'iPhone13,2': ('iPhone 12', 115, 185), 'iPhone13,1': ('iPhone 12 mini', 95, 160),
    'iPhone13,3': ('iPhone 12 Pro', 150, 240), 'iPhone13,4': ('iPhone 12 Pro Max', 180, 290),
    'iPhone14,5': ('iPhone 13', 160, 250), 'iPhone14,2': ('iPhone 13 Pro', 220, 340),
}
SEVERITY = [(('Leve', 'Light'), .06), (('Medio', 'Medium'), .16), (('Grave', 'Severe'), .30)]

PARTS = [
    (('Cristal trasero roto', 'Cracked back glass'), .14, True),
    (('Pantalla agrietada/rota', 'Cracked/broken screen'), .28, True),
    (('Pantalla con manchas o táctil defectuoso', 'Screen stains or faulty touch'), .32, True),
    (('Carcasa doblada o golpes fuertes', 'Bent frame or heavy dents'), .14, True),
    (('Cámara trasera no funciona o lente rota', 'Rear camera not working or broken lens'), .32, False),
    (('Cámara frontal no funciona', 'Front camera not working'), .26, False),
    (('Face ID / Touch ID no funciona', 'Face ID / Touch ID not working'), .40, False),
    (('Conector de carga dañado / no carga', 'Damaged charging port / not charging'), .34, False),
    (('Altavoz o micrófono no funciona', 'Speaker or microphone not working'), .28, False),
    (('Daño por líquido / corrosión', 'Liquid damage / corrosion'), .61, False),
    (('Wi-Fi / Bluetooth / móvil falla', 'Wi-Fi / Bluetooth / cellular failure'), .41, False),
    (('Botones o interruptor no funcionan', 'Buttons or switch not working'), .26, False),
    (('No enciende o reinicia', 'Won’t power on or keeps rebooting'), .76, False),
]
BATTERY = [(('90–100%', '90–100%'), 1.0), (('80–89%', '80–89%'), .88),
           (('Menos de 80%', 'Below 80%'), .68), (('Aviso de servicio', 'Service warning'), .68)]
DEFAULT_CAPS = [64, 128, 256, 512, 1024]

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QHeaderView, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CheckBox, ComboBox, DisplayLabel, StrongBodyLabel,
                            FluentIcon as FIF, PrimaryPushButton, SmoothScrollArea, TableWidget)

from .. import i18n, privacy, theme
from ..i18n import tr
from .components import Page, card_frame, section


class ConditionTab(Page):

    def __init__(self, monitor, parent=None):
        super().__init__("value", ("Estado y valor", "Condition & value"),
                         ("Lee los identificadores del iPhone y estima su precio de venta según daños.",
                          "Reads the iPhone identifiers and estimates its resale price based on damage."), parent=parent)
        self.monitor = monitor
        self.state = {"mode": "none"}
        self._reveal = privacy.Reveal()
        self._serial_rows = []
        self.current_model, self.current_model_name = "", "iPhone"

        cols = QHBoxLayout()
        cols.setSpacing(14)
        self.body.addLayout(cols, 1)

        left_area = SmoothScrollArea()
        left_area.setWidgetResizable(True)
        left_area.setFrameShape(QFrame.Shape.NoFrame)
        left_area.enableTransparentBackground()
        left_inner = QWidget()
        left_inner.setStyleSheet("background: transparent")
        left = QVBoxLayout(left_inner)
        left.setContentsMargins(0, 0, 10, 0)
        left.setSpacing(8)
        left_area.setWidget(left_inner)
        left.addWidget(section("Identificadores disponibles por software", "Identifiers available from software"))
        id_card, il = card_frame(margins=(10, 8, 10, 8))
        self.serials = TableWidget()
        self.serials.setBorderVisible(False)
        self.serials.setColumnCount(2)
        self.serials.verticalHeader().hide()
        self.serials.horizontalHeader().hide()
        self.serials.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.serials.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.serials.setFixedHeight(190)
        self.note = CaptionLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color:{theme.MUTED}")
        i18n.bind(self.note, "setText",
                  "iOS no expone el número de serie de cada pieza; lo que falta no se puede inferir.",
                  "iOS does not expose a serial for every part; missing ones can’t be inferred.")
        privacy.connect_clicks(self.serials, lambda: self._serial_rows, self._reveal, self._fill_serials)
        privacy.bus.changed.connect(lambda: (self._reveal.reset(), self._fill_serials()))
        il.addWidget(self.serials)
        il.addWidget(self.note)
        left.addWidget(id_card)

        left.addWidget(section("Inspección física (manual)", "Physical inspection (manual)"))
        insp_card, nl = card_frame(spacing=10)
        r1 = QHBoxLayout()
        r1.addWidget(i18n.bind(BodyLabel(), "setText", "Almacenamiento *", "Storage *"), 1)
        self.storage = ComboBox()
        self.storage.setMinimumWidth(150)
        r1.addWidget(self.storage)
        r2 = QHBoxLayout()
        r2.addWidget(i18n.bind(BodyLabel(), "setText", "Salud de la batería *", "Battery health *"), 1)
        self.battery = ComboBox()
        self.battery.setMinimumWidth(150)
        self._fill_battery()
        r2.addWidget(self.battery)
        self.req_note = CaptionLabel("")
        self.req_note.setWordWrap(True)
        i18n.bind(self.req_note, "setText",
                  "* Obligatorio: sin el almacenamiento y la salud de la batería no se calcula el valor estimado.",
                  "* Required: the estimated value is not shown until storage and battery health are set.")
        nl.addLayout(r1)
        nl.addLayout(r2)
        nl.addWidget(self.req_note)
        self._storage_by_model = {
            "iPhone10,1": [64, 256], "iPhone10,4": [64, 256], "iPhone10,2": [64, 256], "iPhone10,5": [64, 256],
            "iPhone12,8": [64, 128, 256], "iPhone14,6": [64, 128, 256], "iPhone11,8": [64, 128, 256],
            "iPhone12,1": [64, 128, 256], "iPhone13,1": [64, 128, 256], "iPhone13,2": [64, 128, 256],
            "iPhone13,3": [128, 256, 512], "iPhone13,4": [128, 256, 512],
            "iPhone14,5": [128, 256, 512], "iPhone14,2": [128, 256, 512],
        }
        left.addWidget(insp_card)

        left.addWidget(section("Daños / fallos", "Damage / faults"))
        defects_card, bl = card_frame(margins=(14, 10, 14, 10), spacing=8)
        hint = CaptionLabel("")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.MUTED}")
        i18n.bind(hint, "setText",
                  "Marca lo que no funciona. Solo los daños físicos (pantalla, cristal, carcasa) piden la gravedad; "
                  "lo que funciona o no (Face ID, cámaras, conector…) se marca sin más.",
                  "Tick what is not working. Only physical damage (screen, glass, frame) asks for a severity; "
                  "things that either work or don’t (Face ID, cameras, port…) are just ticked.")
        bl.addWidget(hint)
        self.defect_rows = []
        for (es, en), weight, graded in PARTS:
            row = QHBoxLayout()
            cb = CheckBox()
            i18n.bind(cb, "setText", es, en)
            cb.toggled.connect(self.calculate)
            row.addWidget(cb, 1)
            level = None
            if graded:
                level = ComboBox()
                for (les, len_), factor in SEVERITY:
                    level.addItem(tr(les, len_), userData=factor)
                level.setCurrentIndex(1)
                level.setEnabled(False)
                level.setMinimumWidth(120)
                cb.toggled.connect(level.setEnabled)
                level.currentIndexChanged.connect(self.calculate)
                row.addWidget(level)
            bl.addLayout(row)
            self.defect_rows.append((cb, level, weight, (es, en)))
        left.addWidget(defects_card)
        left.addStretch(1)

        right = QVBoxLayout()
        right.addWidget(section("Valor estimado", "Estimated value"))
        res_card, rl = card_frame(spacing=6)
        self.model_lbl = StrongBodyLabel("")
        self.eur = DisplayLabel("—")
        self.eur.setStyleSheet(f"color:{theme.ACCENT}; font-size:38px; font-weight:700")
        self.usd = BodyLabel("")
        self.usd.setWordWrap(True)
        self.usd.setStyleSheet(f"color:{theme.MUTED}")
        self.issues = CaptionLabel("")
        self.issues.setWordWrap(True)
        self.disclaimer = CaptionLabel("")
        self.disclaimer.setWordWrap(True)
        self.disclaimer.setStyleSheet(f"color:{theme.MUTED}")
        i18n.bind(self.disclaimer, "setText",
                  "Rango orientativo de venta entre particulares; no es una tasación oficial ni una oferta en tiempo real. "
                  "Almacenamiento, bloqueo de activación, mercado y coste de reparación pueden cambiarlo.",
                  "Indicative private-sale range, not a formal appraisal or live offer. Storage, activation lock, market and "
                  "repair costs can change it.")
        rl.addWidget(self.model_lbl)
        rl.addWidget(self.eur)
        rl.addWidget(self.usd)
        rl.addSpacing(6)
        rl.addWidget(self.issues)
        rl.addStretch(1)
        rl.addWidget(self.disclaimer)
        right.addWidget(res_card, 1)

        right_wrap = QWidget()
        right_wrap.setFixedWidth(330)
        right_wrap.setLayout(right)
        right.setContentsMargins(0, 0, 0, 0)
        cols.addWidget(left_area, 1)
        cols.addWidget(right_wrap)

        self.storage.currentIndexChanged.connect(self.calculate)
        self.battery.currentIndexChanged.connect(self.calculate)
        monitor.changed.connect(self.on_state)
        i18n.on_change(self._retranslate)
        self.on_state(monitor.state)

    def on_state(self, state):
        self.state = state
        info = state.get("info") or {}
        candidates = [(tr("Nº de serie del dispositivo", "Device serial number"), info.get("SerialNumber")),
                      (tr("Serie placa lógica (MLB)", "Logic board serial (MLB)"), info.get("MLBSerialNumber")),
                      (tr("Serie banda base", "Baseband serial"), info.get("BasebandSerialNumber")),
                      (tr("Identificador de modelo", "Model identifier"), info.get("ProductType")),
                      (tr("Modelo de hardware", "Hardware model"), info.get("HardwareModel")),
                      ("ECID / chip ID", info.get("UniqueChipID"))]
        rows = [(k, str(v)) for k, v in candidates if v not in (None, "", "N/A")]
        extra = state.get("extra") or {}
        if isinstance(extra, dict):
            for k, v in extra.items():
                if ("serial" in str(k).lower() or "part" in str(k).lower()) and v and not isinstance(v, (dict, list)):
                    rows.append((str(k), str(v)))
        self._serial_rows = rows
        self.serials.setFixedHeight(max(46, min(230, 38 * len(rows) + 4)))
        self._fill_serials()
        model = info.get("ProductType") or state.get("product") or ""
        self.current_model = model
        self.current_model_name = MODEL_BASE.get(model, (model or "iPhone", 40, 100))[0]
        caps = self._storage_by_model.get(model) or DEFAULT_CAPS
        prev = (self.storage.currentData() if self.storage.count() else 0) or 0
        self.storage.blockSignals(True)
        self.storage.clear()
        self.storage.addItem(tr("Selecciona…", "Select…"), userData=0)
        for gb in caps:
            self.storage.addItem(f"{gb} GB" if gb < 1024 else "1 TB", userData=gb)
        i = self.storage.findData(prev) if prev else 0
        self.storage.setCurrentIndex(i if i >= 0 else 0)
        self.storage.blockSignals(False)
        self.calculate()

    def _fill_serials(self):
        privacy.fill_table(self.serials, self._serial_rows, self._reveal)

    def _fill_battery(self):
        self.battery.blockSignals(True)
        self.battery.clear()
        self.battery.addItem(tr("Selecciona…", "Select…"), userData=None)
        for (es, en), factor in BATTERY:
            self.battery.addItem(tr(es, en), userData=factor)
        self.battery.setCurrentIndex(0)
        self.battery.blockSignals(False)

    def _retranslate(self, _code):
        self.battery.setItemText(0, tr("Selecciona…", "Select…"))
        for i, ((es, en), _f) in enumerate(BATTERY, start=1):
            self.battery.setItemText(i, tr(es, en))
        for _cb, level, _w, _n in self.defect_rows:
            if level is None:
                continue
            for i, ((es, en), _f) in enumerate(SEVERITY):
                level.setItemText(i, tr(es, en))
        self.on_state(self.state)

    def calculate(self, *_):
        model = self.current_model
        name, low, high = MODEL_BASE.get(model, (self.current_model_name, 40, 100))
        known = model in MODEL_BASE
        gb = self.storage.currentData() or 0
        battery_factor = self.battery.currentData()
        no_storage, no_battery = not gb, battery_factor is None
        self.model_lbl.setText(name if model else tr("Conecta un iPhone o marca los daños", "Connect an iPhone or tick damage"))
        missing = no_storage or no_battery
        self.req_note.setStyleSheet(f"color:{theme.WARN if missing else theme.MUTED}")
        self.issues.setStyleSheet(f"color:{theme.WARN}" if missing else "color:#cfd3da")
        if missing:
            self.eur.setText("—")
            self.usd.setText("")
            if no_storage and no_battery:
                msg = tr("Indica el almacenamiento y la salud de la batería para ver el valor estimado.",
                         "Select the storage and battery health to see the estimated value.")
            elif no_storage:
                msg = tr("Indica el almacenamiento para ver el valor estimado.",
                         "Select the storage to see the estimated value.")
            else:
                msg = tr("Indica la salud de la batería para ver el valor estimado.",
                         "Select the battery health to see the estimated value.")
            self.issues.setText(msg)
            return
        low *= battery_factor
        high *= battery_factor
        reduction, selected = 0.0, []
        for cb, level, weight, (es, en) in self.defect_rows:
            if cb.isChecked():
                factor = float(level.currentData() or 0) if level is not None else 0.0
                reduction = 1 - (1 - reduction) * (1 - min(.85, weight + factor))
                selected.append(f"{tr(es, en)} ({level.currentText()})" if level is not None else tr(es, en))
        low *= (1 - reduction)
        high *= (1 - reduction)
        bonus = {128: (5, 10), 256: (10, 20), 512: (20, 35), 1024: (30, 50)}.get(gb)
        if bonus:
            low += bonus[0]; high += bonus[1]
        self.eur.setText(f"€{low:.0f}–{high:.0f}")
        self.usd.setText(tr(f"≈ ${round(low / .86)}–{round(high / .86)} USD (conversión aproximada)",
                            f"≈ ${round(low / .86)}–{round(high / .86)} USD (approx. conversion)"))
        extra = "" if known or not model else tr("\nModelo sin tabla propia: se usa un rango genérico.", "\nModel not in the price table: generic range used.")
        if selected:
            self.issues.setText(tr("Problemas marcados: ", "Selected issues: ") + ", ".join(selected) + extra)
        else:
            self.issues.setText(tr("Sin daños marcados: se asume funcionamiento normal.", "No damage ticked: assuming normal working condition.") + extra)

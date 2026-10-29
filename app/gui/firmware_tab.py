import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon
from PySide6.QtWidgets import (QGridLayout, QSizePolicy, QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QStackedWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, CheckBox, FluentIcon as FIF, LineEdit, PrimaryPushButton,
                            ProgressBar, PushButton, SegmentedWidget, StrongBodyLabel, SubtitleLabel, TableWidget,
                            TransparentPushButton, SearchLineEdit, IndeterminateProgressBar)

from .. import i18n, settings, theme
from ..core import catalog, ipsw_api
from ..core.downloader import Cancelled, DownloadJob
from ..core.util import fmt_bytes, fmt_speed
from ..dispatch import post, run_async
from ..i18n import tr
from .components import Page, card_frame, section, toast
from .images import ImageLoader, fit, placeholder

PAGE_CATS, PAGE_DEVS, PAGE_FW = 0, 1, 2
TILE_QSS = f"""
QListWidget {{ background: transparent; border: none; outline: 0; }}
QListWidget::item {{ border-radius: 12px; padding: 6px; color: #d7dae0; }}
QListWidget::item:hover {{ background: #23272d; }}
QListWidget::item:selected {{ background: #12392c; color: white; border: 1px solid {theme.ACCENT}; }}
"""


def _tiles(size, wrap=True):
    lw = QListWidget()
    lw.setViewMode(QListWidget.ViewMode.IconMode)
    lw.setIconSize(QSize(size, size))
    lw.setGridSize(QSize(size + 44, size + 62))
    lw.setResizeMode(QListWidget.ResizeMode.Adjust)
    lw.setMovement(QListWidget.Movement.Static)
    lw.setWordWrap(True)
    lw.setSpacing(6)
    lw.setWrapping(wrap)
    lw.setUniformItemSizes(True)
    lw.setFrameShape(QListWidget.Shape.NoFrame)
    lw.setStyleSheet(TILE_QSS)
    return lw


class DownloadedPanel(QWidget):

    def __init__(self, use_callback, parent=None):
        super().__init__(parent)
        self.use_callback = use_callback
        self.list = QListWidget()
        self.list.setStyleSheet(TILE_QSS)
        self.list.setIconSize(QSize(28, 28))
        self.list.setSpacing(2)
        self.list.itemDoubleClicked.connect(lambda *_: self.use_selected())
        self.status = CaptionLabel("")
        self.status.setStyleSheet(f"color:{theme.MUTED}")
        self.b_use = PrimaryPushButton(FIF.SEND, "")
        self.b_open = PushButton(FIF.FOLDER, "")
        self.b_refresh = PushButton(FIF.SYNC, "")
        self.b_del = PushButton(FIF.DELETE, "")
        for b, es, en in ((self.b_use, "Usar en Flasheo", "Use in Flash"), (self.b_open, "Abrir carpeta", "Open folder"),
                          (self.b_refresh, "Actualizar", "Refresh"), (self.b_del, "Eliminar", "Delete")):
            i18n.bind(b, "setText", es, en)
        self.b_use.clicked.connect(self.use_selected)
        self.b_open.clicked.connect(self.open_folder)
        self.b_refresh.clicked.connect(self.refresh)
        self.b_del.clicked.connect(self.delete_selected)
        row = QHBoxLayout()
        for b in (self.b_use, self.b_open, self.b_refresh, self.b_del):
            row.addWidget(b)
        row.addStretch(1)
        card, cl = card_frame()
        cl.addWidget(self.list, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.addLayout(row)
        lay.addWidget(card, 1)
        lay.addWidget(self.status)
        self.list.itemSelectionChanged.connect(self._sel)
        i18n.on_change(lambda _c: self.refresh())
        self.refresh()

    def _sel(self):
        has = self.list.currentItem() is not None
        self.b_use.setEnabled(has)
        self.b_del.setEnabled(has)

    def refresh(self):
        self.list.clear()
        folder = Path(settings.ipsw_dir())
        folder.mkdir(parents=True, exist_ok=True)
        files = sorted(folder.glob("*.ipsw"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files:
            size = f.stat().st_size
            size_text = f"{size / 1024 ** 3:.2f} GB" if size >= 1024 ** 3 else f"{size / 1024 ** 2:.0f} MB"
            it = QListWidgetItem(FIF.ZIP_FOLDER.icon(), f"{f.name}    ·    {size_text}")
            it.setData(Qt.ItemDataRole.UserRole, str(f))
            it.setToolTip(str(f))
            self.list.addItem(it)
        self.status.setText(tr(f"{len(files)} archivo(s) IPSW · {folder}", f"{len(files)} IPSW file(s) · {folder}") if files else
                            tr("Aún no hay firmwares descargados. Aparecerán aquí al descargarlos.",
                               "No firmware downloaded yet. Files appear here once downloaded."))
        self._sel()

    def selected_path(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def open_folder(self):
        folder = settings.ipsw_dir()
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def use_selected(self):
        p = self.selected_path()
        if p and self.use_callback:
            self.use_callback(p)

    def delete_selected(self):
        p = self.selected_path()
        if not p:
            return
        if QMessageBox.question(self, "VeyloraDevice", tr("¿Eliminar este archivo IPSW? No se puede deshacer.",
                                                    "Delete this IPSW file? This cannot be undone.")) != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(p)
            self.refresh()
        except OSError as e:
            toast(self, "err", "Error", str(e), 6000)


class FirmwareTab(Page):
    ipsw_ready = Signal(str)

    def __init__(self, monitor=None, parent=None):
        super().__init__("firmware", ("Firmware", "Firmware"),
                         ("Busca tu dispositivo, descarga el IPSW y mándalo a Flasheo.",
                          "Find your device, download the IPSW and send it to Flash."), parent=parent)
        self.loader = ImageLoader()
        self.api_devs, self.name_by_ident, self.img_by_ident = [], {}, {}
        self.cats, self.latest = [], []
        self.cur_code = self.cur_ident = None
        self.fws, self.shown = [], []
        self.job = None
        self._conn_ident = ""
        self._devs_sig = None
        self._hist = [("cats",)]
        self._hpos = 0

        self.seg = SegmentedWidget()
        self.seg.addItem("catalog", tr("Catálogo", "Catalogue"), lambda: self._set_tab(0))
        self.seg.addItem("local", tr("Descargados", "Downloaded"), lambda: self._set_tab(1))
        self.seg.setCurrentItem("catalog")
        i18n.on_change(lambda _c: (self.seg.widget("catalog").setText(tr("Catálogo", "Catalogue")),
                                   self.seg.widget("local").setText(tr("Descargados", "Downloaded"))))
        segrow = QGridLayout()
        for col in (0, 1, 2):
            segrow.setColumnStretch(col, 1)
        left = QHBoxLayout()
        self.b_back = TransparentPushButton(FIF.LEFT_ARROW, "")
        i18n.bind(self.b_back, "setText", "Volver", "Back")
        self.b_back.clicked.connect(self._back)
        self.b_fwd = TransparentPushButton(FIF.RIGHT_ARROW, "")
        i18n.bind(self.b_fwd, "setText", "Adelante", "Forward")
        self.b_fwd.clicked.connect(self._forward)
        self.crumbs = CaptionLabel("")
        self.crumbs.setStyleSheet(f"color:{theme.MUTED}")
        left.addWidget(self.b_back)
        left.addWidget(self.b_fwd)
        left.addStretch(1)
        segrow.addLayout(left, 0, 0)
        segrow.addWidget(self.seg, 0, 1, Qt.AlignmentFlag.AlignCenter)
        segrow.addWidget(self.crumbs, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.body.addLayout(segrow)

        self.main = QStackedWidget()
        self.body.addWidget(self.main, 1)
        self.stack = QStackedWidget()
        self.main.addWidget(self.stack)
        self.local = DownloadedPanel(lambda p: self.ipsw_ready.emit(p))
        self.main.addWidget(self.local)

        self.conn_btn = PrimaryPushButton(FIF.PHONE, "")
        self.conn_btn.clicked.connect(lambda: self.open_device(self._conn_ident))
        self.conn_btn.setVisible(False)
        self.cat_list = _tiles(120)
        self.cat_list.itemClicked.connect(lambda it: self.open_category(*it.data(Qt.ItemDataRole.UserRole)))
        self.latest_lbl = section("Últimos dispositivos añadidos", "Recently added devices")
        self.latest_list = _tiles(80, wrap=False)
        self.latest_list.setFixedHeight(160)
        self.latest_list.itemClicked.connect(lambda it: self.open_device(*it.data(Qt.ItemDataRole.UserRole)))
        self.cat_status = CaptionLabel("")
        self.cat_status.setStyleSheet(f"color:{theme.MUTED}")
        b_reload = PushButton(FIF.SYNC, "")
        i18n.bind(b_reload, "setText", "Actualizar catálogo", "Refresh catalogue")
        b_reload.clicked.connect(self.reload_catalog)
        p0 = QWidget()
        l0 = QVBoxLayout(p0)
        l0.setContentsMargins(0, 6, 0, 0)
        l0.addWidget(self.conn_btn)
        l0.addWidget(section("Elige un producto", "Choose a product"))
        l0.addWidget(self.cat_list, 1)
        l0.addWidget(self.latest_lbl)
        l0.addWidget(self.latest_list)
        r0 = QHBoxLayout()
        r0.addWidget(self.cat_status, 1)
        r0.addWidget(b_reload)
        l0.addLayout(r0)

        self.dev_title = SubtitleLabel("")
        self.dev_filter = SearchLineEdit()
        i18n.bind(self.dev_filter, "setPlaceholderText", "Filtrar: 12, Pro, mini…", "Filter: 12, Pro, mini…")
        self.dev_filter.setFixedWidth(260)
        self.dev_filter.textChanged.connect(self._filter_devs)
        self.dev_list = _tiles(104)
        self.dev_list.itemClicked.connect(lambda it: self.open_device(*it.data(Qt.ItemDataRole.UserRole)))
        self.dev_status = CaptionLabel("")
        self.dev_status.setStyleSheet(f"color:{theme.MUTED}")
        p1 = QWidget()
        l1 = QVBoxLayout(p1)
        l1.setContentsMargins(0, 6, 0, 0)
        h1 = QHBoxLayout()
        h1.addWidget(self.dev_title, 1)
        h1.addWidget(self.dev_filter)
        l1.addLayout(h1)
        l1.addWidget(self.dev_list, 1)
        l1.addWidget(self.dev_status)

        self.fw_img = QLabel()
        self.fw_img.setFixedSize(84, 84)
        self.fw_name = SubtitleLabel("")
        self.fw_sub = CaptionLabel("")
        self.fw_sub.setStyleSheet(f"color:{theme.MUTED}")
        self.chk_signed = CheckBox()
        i18n.bind(self.chk_signed, "setText", "Solo firmadas", "Signed only")
        self.chk_signed.toggled.connect(self._fill_table)
        self.table = TableWidget()
        self.table.setBorderVisible(False)
        self.table.setColumnCount(6)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._sel_changed)
        self.table.cellDoubleClicked.connect(lambda *_: self.download())
        self._set_headers()
        i18n.on_change(lambda _c: (self._set_headers(), self._fill_table()))
        self.dir_edit = LineEdit()
        self.dir_edit.setText(settings.ipsw_dir())
        self.dir_edit.setReadOnly(True)
        b_dir = PushButton(FIF.FOLDER, "")
        i18n.bind(b_dir, "setText", "Cambiar carpeta", "Change folder")
        b_dir.clicked.connect(self._pick_dir)
        self.b_dl = PrimaryPushButton(FIF.DOWNLOAD, "")
        i18n.bind(self.b_dl, "setText", "Descargar", "Download")
        self.b_cancel = PushButton(FIF.CANCEL, "")
        i18n.bind(self.b_cancel, "setText", "Cancelar", "Cancel")
        self.b_use = PushButton(FIF.SEND, "")
        i18n.bind(self.b_use, "setText", "Usar en Flasheo", "Use in Flash")
        self.b_dl.clicked.connect(self.download)
        self.b_cancel.clicked.connect(self._cancel)
        self.b_use.clicked.connect(self._use)
        self.bar = ProgressBar()
        self.bar.setRange(0, 1000)
        self.status = CaptionLabel("")
        self.status.setStyleSheet(f"color:{theme.MUTED}")
        p2 = QWidget()
        l2 = QVBoxLayout(p2)
        l2.setContentsMargins(0, 6, 0, 0)
        l2.setSpacing(8)
        head, hl = card_frame(QHBoxLayout, spacing=14)
        hl.addWidget(self.fw_img)
        col = QVBoxLayout()
        col.addWidget(self.fw_name)
        col.addWidget(self.fw_sub)
        hl.addLayout(col, 1)
        hl.addWidget(self.chk_signed)
        l2.addWidget(head)
        l2.addWidget(self.table, 1)
        d = QHBoxLayout()
        d.addWidget(self.dir_edit, 1)
        d.addWidget(b_dir)
        l2.addLayout(d)
        act = QHBoxLayout()
        for b in (self.b_dl, self.b_cancel, self.b_use):
            act.addWidget(b)
        act.addStretch(1)
        l2.addLayout(act)
        l2.addWidget(self.bar)
        l2.addWidget(self.status)

        for p in (p0, p1, p2):
            p.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            self.stack.addWidget(p)
        self.local.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._set_busy(False)
        self._sel_changed()
        self._show(PAGE_CATS)

        i18n.on_change(lambda _c: (self._update_crumbs(), self._update_conn_btn()))
        if monitor:
            monitor.changed.connect(self._on_state)
            self._on_state(monitor.state)
        self._load_home(from_cache=True)
        run_async(ipsw_api.get_devices, self._api_ok, lambda e: None)

    def _set_tab(self, i):
        if i == 1:
            self.local.refresh()
        self.main.setCurrentIndex(i)
        self.crumbs.setVisible(i == 0)
        self._update_nav()

    def _set_headers(self):
        self.table.setHorizontalHeaderLabels([tr("Versión", "Version"), "Build", tr("Firmada", "Signed"),
                                              tr("Tamaño", "Size"), tr("Fecha", "Date"), tr("En disco", "On disk")])

    def _show(self, idx):
        self.stack.setCurrentIndex(idx)
        self._update_crumbs()
        self._update_nav()

    def _update_crumbs(self):
        names = [tr("Productos", "Products"), tr("Dispositivos", "Devices"), tr("Versiones", "Versions")]
        self.crumbs.setText("  ›  ".join(names[: self.stack.currentIndex() + 1]))

    def _update_nav(self):
        on_catalog = self.main.currentIndex() == 0
        idle = self.job is None
        self.b_back.setVisible(on_catalog)
        self.b_fwd.setVisible(on_catalog)
        self.b_back.setEnabled(idle and self._hpos > 0)
        self.b_fwd.setEnabled(idle and self._hpos < len(self._hist) - 1)

    def _push(self, entry):
        del self._hist[self._hpos + 1:]
        self._hist.append(entry)
        self._hpos = len(self._hist) - 1
        self._update_nav()

    def _back(self):
        self._step(-1)

    def _forward(self):
        self._step(1)

    def _step(self, d):
        pos = self._hpos + d
        if self.job or not 0 <= pos < len(self._hist):
            return
        self._hpos = pos
        entry = self._hist[pos]
        if entry[0] == "cats":
            self._show(PAGE_CATS)
        elif entry[0] == "devs":
            _, code, name = entry
            if self.cur_code == code and self.dev_list.count():
                self._show(PAGE_DEVS)
            else:
                self.open_category(code, name, push=False)
        else:
            _, ident, name = entry
            if self.cur_ident == ident and self.fws:
                self._show(PAGE_FW)
            else:
                self.open_device(ident, name, push=False)
        self._update_nav()

    def show_catalog(self):
        self.seg.setCurrentItem("catalog")
        self._set_tab(0)

    def reload_catalog(self):
        self._load_home(from_cache=False)

    def _load_home(self, from_cache):
        cached = catalog.load_cache("home") if from_cache else None
        if cached:
            self._home_ok(cached, quiet=True)
        else:
            self.cat_status.setText(tr("Cargando productos de ipsw.me…", "Loading products from ipsw.me…"))
        run_async(catalog.fetch_home, self._home_ok,
                  lambda e: self.cat_status.setText(tr(f"Sin conexión con ipsw.me ({e}). Se usa lo guardado.",
                                                       f"Can’t reach ipsw.me ({e}). Using saved data.")))
        if not cached:
            self._home_ok({"categories": [{"code": c, "name": n, "img": None} for c, n in catalog.FALLBACK_CATEGORIES],
                           "latest": []}, quiet=True)

    def _home_ok(self, data, quiet=False):
        cats, latest = data["categories"], data["latest"]
        if (cats, latest) == (self.cats, self.latest):
            return
        self.cats, self.latest = cats, latest
        self.cat_list.clear()
        for c in cats:
            it = QListWidgetItem(QIcon(placeholder(c["name"], 120)), c["name"])
            it.setData(Qt.ItemDataRole.UserRole, (c["code"], c["name"]))
            self.cat_list.addItem(it)
            self.loader.icon_into(it, c["img"], 120)
        self.latest_list.clear()
        for d in latest:
            self.name_by_ident[d["ident"]] = d["name"]
            if d["img"]:
                self.img_by_ident[d["ident"]] = d["img"]
            it = QListWidgetItem(QIcon(placeholder(d["name"], 80)), d["name"])
            it.setData(Qt.ItemDataRole.UserRole, (d["ident"], d["name"]))
            it.setToolTip(f'{d["name"]} ({d["ident"]})')
            self.latest_list.addItem(it)
            self.loader.icon_into(it, d["img"], 80)
        self.latest_lbl.setVisible(bool(latest))
        self.latest_list.setVisible(bool(latest))
        if not quiet:
            self.cat_status.setText(tr(f"{len(cats)} productos · catálogo actualizado", f"{len(cats)} products · catalogue updated"))

    def _api_ok(self, devs):
        self.api_devs = devs
        for d in devs:
            self.name_by_ident.setdefault(d["identifier"], d.get("name") or d["identifier"])
        self._update_conn_btn()

    def _on_state(self, s):
        ident = ""
        if s["mode"] == "normal" and s.get("info"):
            ident = s["info"].get("ProductType", "")
        elif s["mode"] == "recovery":
            ident = s.get("product", "")
        self._conn_ident = ident
        self._update_conn_btn()

    def _update_conn_btn(self):
        ident = self._conn_ident
        self.conn_btn.setVisible(bool(ident))
        if ident:
            name = self.name_by_ident.get(ident, ident)
            self.conn_btn.setText(tr(f"Tu dispositivo conectado: {name} ({ident})  →  ver sus firmwares",
                                     f"Your connected device: {name} ({ident})  →  see its firmware"))

    def open_category(self, code, name, push=True):
        self.cur_code = code
        self.dev_title.setText(name)
        self.dev_filter.clear()
        self.dev_list.clear()
        self._devs_sig = None
        cached = catalog.load_cache(f"devices_{code}")
        if cached:
            self._fill_devs(code, cached)
            self.dev_status.setText(tr("Actualizando…", "Updating…"))
        else:
            self.dev_status.setText(tr("Cargando dispositivos…", "Loading devices…"))
        self._show(PAGE_DEVS)
        if push:
            self._push(("devs", code, name))
        api = list(self.api_devs)

        def ok(lst):
            if self.cur_code == code:
                self._fill_devs(code, lst, if_changed=True)

        run_async(lambda: catalog.fetch_category_devices(code, api), ok,
                  lambda e: self.dev_status.setText(tr(f"No pude actualizar ({e}). Se muestra lo guardado.",
                                                       f"Couldn’t update ({e}). Showing saved data.")))

    def _fill_devs(self, code, devs, if_changed=False):
        sig = [d["ident"] for d in devs]
        if if_changed and self._devs_sig == sig:
            self.dev_status.setText(tr(f"{len(devs)} dispositivos", f"{len(devs)} devices"))
            return
        self._devs_sig = sig
        self.dev_list.clear()
        for d in devs:
            self.name_by_ident[d["ident"]] = d["name"]
            if d["img"]:
                self.img_by_ident[d["ident"]] = d["img"]
            it = QListWidgetItem(QIcon(placeholder(d["name"], 104)), d["name"])
            it.setData(Qt.ItemDataRole.UserRole, (d["ident"], d["name"]))
            it.setToolTip(f'{d["name"]} ({d["ident"]})')
            self.dev_list.addItem(it)
            self.loader.icon_into(it, d["img"] or self.img_by_ident.get(d["ident"]), 104)
        self.dev_status.setText(tr(f"{len(devs)} dispositivos · los más nuevos primero",
                                   f"{len(devs)} devices · newest first"))
        self._filter_devs(self.dev_filter.text())

    def _filter_devs(self, text):
        t = text.strip().lower()
        for i in range(self.dev_list.count()):
            it = self.dev_list.item(i)
            ident = it.data(Qt.ItemDataRole.UserRole)[0]
            it.setHidden(bool(t) and t not in (it.text() + " " + ident).lower())

    def set_identifier(self, ident, load=True):
        if ident:
            self.show_catalog()
            self.open_device(ident)

    def open_device(self, ident, name=None, push=True):
        if not ident or self.job:
            return
        name = name or self.name_by_ident.get(ident) or ident
        self.cur_ident = ident
        self.fw_name.setText(name)
        self.fw_sub.setText(ident)
        self.fw_img.setPixmap(placeholder(name, 84))
        url = self.img_by_ident.get(ident)
        if url:
            self.loader.get(url, lambda pm: self.fw_img.setPixmap(fit(pm, 84)))
        else:
            code = catalog.category_of_identifier(ident)
            if code:
                api = list(self.api_devs)

                def got(lst):
                    for d in lst:
                        if d["img"]:
                            self.img_by_ident.setdefault(d["ident"], d["img"])
                    u = self.img_by_ident.get(ident)
                    if u and self.cur_ident == ident:
                        self.loader.get(u, lambda pm: self.fw_img.setPixmap(fit(pm, 84)))

                run_async(lambda: catalog.fetch_category_devices(code, api), got, lambda e: None)
        self.fws, self.shown = [], []
        self.table.setRowCount(0)
        self.bar.setValue(0)
        self.status.setText(tr(f"Pidiendo versiones de {name} a ipsw.me…", f"Requesting {name} versions from ipsw.me…"))
        self._show(PAGE_FW)
        if push:
            self._push(("fw", ident, name))

        def ok(fws):
            if self.cur_ident != ident:
                return
            self.fws = fws
            self._fill_table()
            self.status.setText(tr(f"{len(fws)} versiones. Doble clic o «Descargar» para bajar la seleccionada.",
                                   f"{len(fws)} versions. Double-click or “Download” to get the selected one."))
            for r, f in enumerate(self.shown):
                if f.get("signed"):
                    self.table.selectRow(r)
                    break

        run_async(lambda: ipsw_api.get_firmwares(ident), ok,
                  lambda e: self.status.setText(tr(f"Error pidiendo versiones: {e}", f"Error fetching versions: {e}")))

    def _fill_table(self, *_):
        only = self.chk_signed.isChecked()
        self.shown = [f for f in self.fws if f.get("signed") or not only]
        self.table.setRowCount(len(self.shown))
        for r, f in enumerate(self.shown):
            on_disk = os.path.exists(self._dest(f))
            vals = [f.get("version", ""), f.get("buildid", ""), "✔" if f.get("signed") else "✘",
                    fmt_bytes(f.get("filesize", 0)), (f.get("releasedate") or f.get("uploaddate") or "")[:10],
                    "✔" if on_disk else ""]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 2:
                    it.setForeground(QColor(theme.ACCENT if f.get("signed") else theme.DANGER))
                self.table.setItem(r, c, it)
        self._sel_changed()

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        return self.shown[rows[0].row()] if rows and rows[0].row() < len(self.shown) else None

    def _dest(self, fw):
        return os.path.join(settings.ipsw_dir(), os.path.basename(fw["url"]))

    def _sel_changed(self):
        fw = self._selected()
        self.b_dl.setEnabled(fw is not None and self.job is None)
        self.b_use.setEnabled(fw is not None and os.path.exists(self._dest(fw)))

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr("Carpeta de descargas IPSW", "IPSW download folder"), settings.ipsw_dir())
        if d:
            settings.set_ipsw_dir(d)
            self.dir_edit.setText(d)
            self._fill_table()
            self.local.refresh()

    def _set_busy(self, busy):
        self.b_cancel.setEnabled(busy)
        self.b_dl.setEnabled(not busy)
        self._update_nav()

    def download(self):
        fw = self._selected()
        if not fw or self.job:
            return
        if not fw.get("signed"):
            if QMessageBox.question(self, tr("Firmware no firmado", "Unsigned firmware"),
                                    tr("Esta versión ya NO está firmada por Apple: la podrás descargar, pero no restaurar "
                                       "(salvo con SHSH blobs). ¿Descargar igualmente?",
                                       "This version is no longer signed by Apple: you can download it but not restore it "
                                       "(except with SHSH blobs). Download anyway?")) != QMessageBox.StandardButton.Yes:
                return
        job = DownloadJob(fw["url"], self._dest(fw), fw.get("sha1sum"), fw.get("filesize") or 0)
        self.job = job
        self._set_busy(True)
        self.bar.setValue(0)

        def work():
            return job.run(lambda d, t, s: post(lambda: self._progress(d, t, s)),
                           lambda m: post(lambda: self.status.setText(m)))

        run_async(work, self._dl_ok, self._dl_fail)

    def _progress(self, done, total, speed):
        if total:
            self.bar.setValue(int(done * 1000 / total))
        self.status.setText(tr(f"Descargando… {fmt_bytes(done)} / {fmt_bytes(total)}  {fmt_speed(speed)}",
                               f"Downloading… {fmt_bytes(done)} / {fmt_bytes(total)}  {fmt_speed(speed)}"))

    def _dl_ok(self, path):
        self.job = None
        self._set_busy(False)
        self.bar.setValue(1000)
        self.status.setText(tr(f"Listo: {path}", f"Done: {path}"))
        self._fill_table()
        self.local.refresh()
        toast(self, "ok", tr("Descarga completada", "Download complete"), os.path.basename(path), 6000)
        self.ipsw_ready.emit(path)

    def _dl_fail(self, e):
        self.job = None
        self._set_busy(False)
        self._sel_changed()
        if isinstance(e, Cancelled):
            self.status.setText(tr("Descarga cancelada (puedes reanudarla más tarde).", "Download cancelled (you can resume later)."))
        else:
            self.status.setText(f"Error: {e}")
            toast(self, "err", tr("Falló la descarga", "Download failed"), str(e), 8000)

    def _cancel(self):
        if self.job:
            self.job.cancel()

    def _use(self):
        fw = self._selected()
        if fw and os.path.exists(self._dest(fw)):
            self.ipsw_ready.emit(self._dest(fw))

import json
import re

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QProcess, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableView,
                               QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from qfluentwidgets import (Action, CaptionLabel, ComboBox, FluentIcon as FIF, PushButton, RoundMenu,
                            SearchLineEdit, TableWidget)

from .. import privacy, theme
from ..core import device, infomap
from ..core.tools import ToolMissing
from ..i18n import tr
from ..core.terminal import launch_in_terminal
from ..dispatch import run_async


def open_terminal_or_warn(parent, argv):
    if not launch_in_terminal(argv):
        QMessageBox.warning(parent, "Terminal", tr("No encontré ningún terminal (konsole, gnome-terminal, xterm…).",
                                                   "No terminal found (konsole, gnome-terminal, xterm…)."))


class InfoWindow(QDialog):
    def __init__(self, monitor, parent=None, on_report=None):
        super().__init__(parent)
        self.monitor = monitor
        self.on_report = on_report
        self.fields = []
        self.setWindowTitle(tr("Información completa del dispositivo", "Full device information"))
        self.resize(900, 650)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Buscar: serie, IMEI, batería, ECID…", "Search: serial, IMEI, battery, ECID…"))
        self.filter.textChanged.connect(self._apply_filter)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([tr("Campo", "Field"), tr("Valor", "Value"), tr("Clave técnica", "Technical key")])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.status = QLabel("")
        b_ref = QPushButton(tr("Actualizar", "Refresh"))
        b_copy = QPushButton(tr("Copiar", "Copy"))
        b_exp = QPushButton(tr("Exportar…", "Export…"))
        b_term = QPushButton(tr("Ver en terminal", "Open in terminal"))
        b_pdf = QPushButton(tr("Informe PDF…", "PDF report…"))
        b_ref.clicked.connect(self.load)
        b_copy.clicked.connect(self._copy)
        b_exp.clicked.connect(self._export)
        b_term.clicked.connect(self._terminal)
        b_pdf.clicked.connect(lambda: self.on_report and self.on_report())
        row = QHBoxLayout()
        for b in (b_ref, b_copy, b_exp, b_term, b_pdf):
            row.addWidget(b)
        row.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addWidget(self.filter)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.status)
        lay.addLayout(row)
        self._reveal = privacy.Reveal()
        self.tree.itemClicked.connect(self._item_clicked)
        privacy.bus.changed.connect(lambda: (self._reveal.reset(), self._fill(self.fields) if getattr(self, 'fields', None) else None))
        self.load()

    def load(self):
        s = self.monitor.state
        self.status.setText(tr("Leyendo el dispositivo…", "Reading the device…"))
        if s["mode"] == "normal" and s.get("info"):
            udid = s["udid"]
            run_async(lambda: device.get_full(udid),
                      lambda res: self._fill(infomap.flatten(*res)),
                      lambda e: self.status.setText(f"Error: {e}"))
        elif s["mode"] == "recovery":
            self._fill(infomap.from_recovery(s["recovery"]))
        else:
            self.status.setText(tr("No hay ningún dispositivo listo. Conéctalo y confía en este equipo.",
                                   "No device is ready. Connect it and trust this computer."))

    def _shown_value(self, fld):
        return self._reveal.display(fld.label, fld.value)[0]

    def _item_clicked(self, item, column):
        if item.parent() is None or column != 1:
            return
        fld = item.data(0, Qt.ItemDataRole.UserRole + 5)
        if fld is not None and privacy.enabled() and privacy.is_sensitive(fld.label):
            self._reveal.click(fld.label, lambda: self._refresh_item(item, fld))

    def _refresh_item(self, item, fld):
        try:
            item.setText(1, self._shown_value(fld))
        except RuntimeError:
            pass

    def _fill(self, fields):
        self.fields = fields
        self.tree.clear()
        for cat, fs in infomap.group(fields):
            top = QTreeWidgetItem([f"{infomap.category_label(cat)}  ({len(fs)})"])
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            self.tree.addTopLevelItem(top)
            for fld in fs:
                it = QTreeWidgetItem([fld.label, self._shown_value(fld), fld.key])
                it.setData(0, Qt.ItemDataRole.UserRole + 5, fld)
                it.setForeground(2, QBrush(QColor("#7d8890")))
                top.addChild(it)
            top.setExpanded(cat != "other")
        self.status.setText(tr(f"{len(fields)} datos. Pulsa «Otros» para ver el resto de claves del sistema.",
                               f"{len(fields)} items. Open “Other” to see the remaining system keys."))
        self._apply_filter(self.filter.text())

    def _apply_filter(self, text):
        t = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            vis = 0
            for j in range(top.childCount()):
                ch = top.child(j)
                match = not t or any(t in ch.text(c).lower() for c in range(3))
                ch.setHidden(not match)
                vis += match
            top.setHidden(vis == 0)
            if t and vis:
                top.setExpanded(True)

    def _text(self, selected_only):
        items = self.tree.selectedItems() if selected_only else None
        lines = []
        for fld in self.fields:
            lines.append(f"{fld.label}: {privacy.report_value(fld.label, fld.value)}")
        if items:
            lines = [f"{it.text(0)}: {privacy.report_value(it.text(0), it.text(1))}" for it in items if it.parent()]
        return "\n".join(lines)

    def _copy(self):
        QGuiApplication.clipboard().setText(self._text(True))
        self.status.setText(tr("Copiado al portapapeles (lo seleccionado, o todo si no había selección).",
                               "Copied to the clipboard (the selection, or everything if nothing was selected)."))

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Exportar información", "Export information"),
                                              tr("dispositivo.txt", "device.txt"),
                                              tr("Texto (*.txt);;JSON (*.json)", "Text (*.txt);;JSON (*.json)"))
        if not path:
            return
        if path.endswith(".json"):
            ck, fk, vk, kk = (("categoria", "campo", "valor", "clave") if tr("es", "en") == "es"
                              else ("category", "field", "value", "key"))
            data = [{ck: f.category_label, fk: f.label, vk: f.value, kk: f.key} for f in self.fields]
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._text(False) + "\n")
        self.status.setText(tr(f"Guardado en {path}", f"Saved to {path}"))

    def _terminal(self):
        udid = self.monitor.state.get("udid")
        open_terminal_or_warn(self, ["ideviceinfo"] + (["-u", udid] if udid else []))


BUNDLE_ID_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_]*$")


class AppsWindow(QDialog):

    COLS = ("name", "id", "version", "type")

    def __init__(self, monitor, parent=None):
        super().__init__(parent)
        self.monitor = monitor
        self.apps = []
        self.busy = False
        self.setWindowTitle(tr("Aplicaciones instaladas", "Installed apps"))
        self.resize(940, 620)

        self.filter = SearchLineEdit()
        self.filter.setPlaceholderText(tr("Buscar app o identificador…", "Search app or identifier…"))
        self.kind = ComboBox()
        self.kind.addItems([tr("Todas", "All"), tr("Usuario", "User"), tr("Sistema", "System")])
        self.kind.setMinimumWidth(130)
        self.filter.textChanged.connect(self._fill)
        self.kind.currentIndexChanged.connect(self._fill)

        self.table = TableWidget()
        self.table.setBorderVisible(False)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([tr("Nombre", "Name"), tr("Identificador", "Identifier"),
                                              tr("Versión", "Version"), tr("Tipo", "Type")])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._sel_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)

        self.status = CaptionLabel("")
        self.b_ref = PushButton(FIF.SYNC, tr("Actualizar", "Refresh"))
        self.b_term = PushButton(FIF.COMMAND_PROMPT if hasattr(FIF, "COMMAND_PROMPT") else FIF.CODE,
                                 tr("Ver en terminal", "Open in terminal"))
        self.b_del = PushButton(FIF.DELETE, tr("Desinstalar", "Uninstall"))
        self.b_del.setStyleSheet(f"PushButton {{ background:{theme.DANGER}; color:white; border:none; border-radius:8px; padding:6px 16px 6px 36px }}"
                                 f"PushButton:hover {{ background:#f0565b }} PushButton:disabled {{ background:#3a2527; color:#888 }}")
        self.b_del.setEnabled(False)
        self.b_ref.clicked.connect(self.load)
        self.b_term.clicked.connect(self._terminal)
        self.b_del.clicked.connect(self.uninstall_selected)

        top = QHBoxLayout()
        top.addWidget(self.filter, 1)
        top.addWidget(self.kind)
        bot = QHBoxLayout()
        bot.addWidget(self.status, 1)
        bot.addWidget(self.b_del)
        bot.addWidget(self.b_ref)
        bot.addWidget(self.b_term)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addLayout(bot)
        self.load()

    @staticmethod
    def normalize(raw):
        out = []
        for a in raw:
            out.append({"name": a.get("CFBundleDisplayName") or a.get("CFBundleName") or "",
                        "id": a.get("CFBundleIdentifier", ""),
                        "version": a.get("CFBundleShortVersionString") or a.get("CFBundleVersion") or "",
                        "type": a.get("ApplicationType", "")})
        return sorted(out, key=lambda x: x["name"].lower())

    @staticmethod
    def _type_label(t):
        return {"User": tr("Usuario", "User"), "System": tr("Sistema", "System")}.get(t, t)

    def _udid(self):
        s = self.monitor.state
        return s["udid"] if (s["mode"] == "normal" and s.get("info")) else None

    def load(self):
        udid = self._udid()
        if not udid:
            self.status.setText(tr("Necesito un dispositivo conectado y de confianza (modo normal).",
                                   "A connected, trusted device (normal mode) is required."))
            return
        self.status.setText(tr("Leyendo apps… (puede tardar unos segundos)", "Reading apps… (may take a few seconds)"))

        def ok(raw):
            self.apps = self.normalize(raw)
            self._fill()

        run_async(lambda: device.list_apps(udid), ok, lambda e: self.status.setText(f"Error: {e}"))

    def _fill(self, *_):
        t = self.filter.text().strip().lower()
        k = self.kind.currentIndex()
        rows = [a for a in self.apps
                if (not t or t in a["name"].lower() or t in a["id"].lower())
                and (k == 0 or (k == 1) == (a["type"] == "User"))]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, a in enumerate(rows):
            for c, key in enumerate(self.COLS):
                it = QTableWidgetItem(self._type_label(a[key]) if key == "type" else a[key])
                it.setData(Qt.ItemDataRole.UserRole, a)
                self.table.setItem(r, c, it)
        self.table.setSortingEnabled(True)
        self.status.setText(tr(f"{len(rows)} de {len(self.apps)} apps", f"{len(rows)} of {len(self.apps)} apps"))
        self._sel_changed()

    def _selected_apps(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        apps = []
        for r in rows:
            it = self.table.item(r, 0)
            if it is not None:
                apps.append(it.data(Qt.ItemDataRole.UserRole))
        return apps

    def _sel_changed(self):
        self.b_del.setEnabled(not self.busy and any(a["type"] == "User" for a in self._selected_apps()))

    def _menu(self, pos):
        apps = self._selected_apps()
        if not apps:
            return
        m = RoundMenu(parent=self)
        a_copy = Action(FIF.COPY, tr("Copiar identificador", "Copy identifier"))
        a_copy.triggered.connect(lambda *_: QGuiApplication.clipboard().setText("\n".join(a["id"] for a in apps)))
        m.addAction(a_copy)
        if any(a["type"] == "User" for a in apps) and not self.busy:
            a_del = Action(FIF.DELETE, tr("Desinstalar", "Uninstall"))
            a_del.triggered.connect(lambda *_: self.uninstall_selected())
            m.addAction(a_del)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def uninstall_selected(self):
        udid = self._udid()
        apps = self._selected_apps()
        users = [a for a in apps if a["type"] == "User" and BUNDLE_ID_OK.match(a["id"] or "")]
        skipped = len(apps) - len(users)
        if not udid or not users or self.busy:
            return
        names = "\n".join(f"  • {a['name'] or a['id']}  ({a['id']})" for a in users[:8])
        if len(users) > 8:
            names += tr(f"\n  … y {len(users) - 8} más", f"\n  … and {len(users) - 8} more")
        text = tr(f"¿Desinstalar {len(users)} app(s) del dispositivo?\n\n{names}\n\nSe borrarán también sus datos. No se puede deshacer.",
                  f"Uninstall {len(users)} app(s) from the device?\n\n{names}\n\nTheir data will be deleted too. This cannot be undone.")
        if skipped:
            text += tr(f"\n\n({skipped} app(s) del sistema se omiten: iOS no permite quitarlas.)",
                       f"\n\n({skipped} system app(s) skipped: iOS does not allow removing them.)")
        if QMessageBox.warning(self, tr("Desinstalar", "Uninstall"), text,
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                               QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.busy = True
        self.b_del.setEnabled(False)
        self.status.setText(tr(f"Desinstalando {len(users)} app(s)… no desconectes el cable.",
                               f"Uninstalling {len(users)} app(s)… do not unplug the cable."))

        def work():
            results = []
            for a in users:
                try:
                    device.uninstall_app(udid, a["id"])
                    results.append((a, None))
                except Exception as e:
                    results.append((a, str(e)))
            return results

        def done(results):
            self.busy = False
            failed = [(a, err) for a, err in results if err]
            okn = len(results) - len(failed)
            if failed:
                detail = "\n".join(f"• {a['name'] or a['id']}: {err[:160]}" for a, err in failed[:6])
                QMessageBox.warning(self, tr("Algunas apps no se desinstalaron", "Some apps were not uninstalled"),
                                    tr(f"Desinstaladas: {okn}. Con error: {len(failed)}.\n\n{detail}",
                                       f"Uninstalled: {okn}. Failed: {len(failed)}.\n\n{detail}"))
            self.load()
            if not failed:
                self.status.setText(tr(f"Desinstaladas {okn} app(s).", f"Uninstalled {okn} app(s)."))

        def fail(e):
            self.busy = False
            self.status.setText(f"Error: {e}")
            self._sel_changed()

        run_async(work, done, fail)

    def _terminal(self):
        udid = self.monitor.state.get("udid")
        try:
            argv = device.installer_cmd("list_text", udid)
        except ToolMissing as e:
            QMessageBox.warning(self, "ideviceinstaller", str(e))
            return
        open_terminal_or_warn(self, argv)


ANSI = re.compile(r"\x1b\[[0-9;]*m")
RE_LINE = re.compile(r"^(?P<time>[A-Z][a-z]{2}\s+\d+\s+[\d:.]+)\s+(?:(?P<dev>\S+)\s+)?"
                     r"(?P<proc>[^\s\[]+?)(?:\((?P<sub>[^)]*)\))?\[(?P<pid>\d+)\]\s+<(?P<lvl>\w+)>:\s?(?P<msg>.*)$")
LEVEL_COLOR = {"Error": "#ff6b6b", "Fault": "#ff4d4d", "Critical": "#ff4d4d", "Warning": "#ffb347",
               "Info": "#9fb0b8", "Debug": "#707c84"}
MAX_ROWS, KEEP_ROWS, MAX_PENDING, BATCH = 50_000, 40_000, 40_000, 4_000


def parse_line(raw):
    m = RE_LINE.match(raw)
    if not m:
        return ("", "", "", raw, raw)
    proc = m["proc"] + (f' ({m["sub"]})' if m["sub"] else "")
    return (m["time"], proc, m["lvl"], m["msg"], raw)


class LogModel(QAbstractTableModel):
    HEAD = [("Hora", "Time"), ("Proceso", "Process"), ("Nivel", "Level"), ("Mensaje", "Message")]

    def __init__(self):
        super().__init__()
        self.rows = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 4

    def headerData(self, s, o, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and o == Qt.Orientation.Horizontal:
            return tr(*self.HEAD[s])

    def data(self, idx, role=Qt.ItemDataRole.DisplayRole):
        r = self.rows[idx.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return r[idx.column()]
        if role == Qt.ItemDataRole.ForegroundRole:
            c = LEVEL_COLOR.get(r[2])
            return QBrush(QColor(c)) if c else None
        if role == Qt.ItemDataRole.ToolTipRole:
            return r[4]

    def append(self, new):
        n = len(self.rows)
        self.beginInsertRows(QModelIndex(), n, n + len(new) - 1)
        self.rows.extend(new)
        self.endInsertRows()
        if len(self.rows) > MAX_ROWS:
            drop = len(self.rows) - KEEP_ROWS
            self.beginRemoveRows(QModelIndex(), 0, drop - 1)
            del self.rows[:drop]
            self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self.rows = []
        self.endResetModel()


class LogFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.level = ""

    def filterAcceptsRow(self, row, parent):
        r = self.sourceModel().rows[row]
        if self.level and r[2] != self.level:
            return False
        return not self.text or self.text in r[4].lower()


class SyslogWindow(QDialog):

    def __init__(self, monitor, parent=None):
        super().__init__(parent)
        self.monitor = monitor
        self.setWindowTitle(tr("Registro del sistema (syslog) en vivo", "Live system log (syslog)"))
        self.resize(1100, 650)
        self.proc = None
        self._buf = b""
        self._pending = []
        self._dropped = 0

        self.b_toggle = QPushButton(tr("▶ Iniciar", "▶ Start"))
        self.b_toggle.setObjectName("accent")
        self.b_toggle.clicked.connect(self.toggle)
        b_clear = QPushButton(tr("🧹 Limpiar", "🧹 Clear"))
        b_clear.clicked.connect(self._clear)
        b_save = QPushButton(tr("💾 Guardar…", "💾 Save…"))
        b_save.clicked.connect(self._save)
        b_term = QPushButton(tr("🖥 Ver en terminal", "🖥 Open in terminal"))
        b_term.clicked.connect(self._terminal)
        self.chk_quiet = QCheckBox(tr("Ocultar procesos ruidosos", "Hide noisy processes"))
        self.chk_quiet.setChecked(True)
        self.chk_quiet.setToolTip(tr("Usa -q de idevicesyslog (se aplica al iniciar)", "Uses idevicesyslog -q (applied on start)"))
        self.chk_follow = QCheckBox(tr("Seguir al final", "Follow the end"))
        self.chk_follow.setChecked(True)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Filtrar por texto o proceso (p. ej. wifi, SpringBoard, error)…",
                                          "Filter by text or process (e.g. wifi, SpringBoard, error)…"))
        self.level = QComboBox()
        self.level.addItems([tr("Todos los niveles", "All levels"), "Error", "Fault", "Warning", "Notice", "Info", "Debug"])
        self.filter.textChanged.connect(self._refilter)
        self.level.currentIndexChanged.connect(self._refilter)

        self.model = LogModel()
        self.proxy = LogFilter()
        self.proxy.setSourceModel(self.model)
        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(20)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setWordWrap(False)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setColumnWidth(0, 150)
        self.view.setColumnWidth(1, 200)
        self.view.setColumnWidth(2, 70)
        self.status = QLabel(tr("■ Detenido", "■ Stopped"))

        r1 = QHBoxLayout()
        for w in (self.b_toggle, b_clear, b_save, b_term):
            r1.addWidget(w)
        r1.addStretch(1)
        r1.addWidget(self.chk_quiet)
        r1.addWidget(self.chk_follow)
        r2 = QHBoxLayout()
        r2.addWidget(self.filter, 1)
        r2.addWidget(self.level)
        lay = QVBoxLayout(self)
        lay.addLayout(r1)
        lay.addLayout(r2)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.status)

        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._flush)
        self._timer.start()

    def running(self):
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    def toggle(self):
        self.stop() if self.running() else self.start()

    def start(self):
        s = self.monitor.state
        args = ["--no-colors"]
        if self.chk_quiet.isChecked():
            args.append("-q")
        if s.get("udid"):
            args += ["-u", s["udid"]]
        p = QProcess(self)
        p.readyReadStandardOutput.connect(self._on_out)
        p.finished.connect(self._on_finished)
        p.errorOccurred.connect(self._on_error)
        self.proc = p
        self._buf = b""
        p.start("idevicesyslog", args)
        self.b_toggle.setText(tr("■ Detener", "■ Stop"))
        self.b_toggle.setObjectName("danger")
        self.b_toggle.setStyleSheet("")
        self.b_toggle.style().unpolish(self.b_toggle)
        self.b_toggle.style().polish(self.b_toggle)
        self._update_status()

    def stop(self):
        if not self.running():
            return
        p = self.proc
        p.terminate()
        QTimer.singleShot(1200, lambda: p.kill() if p.state() != QProcess.ProcessState.NotRunning else None)
        self.b_toggle.setEnabled(False)
        self.status.setText(tr("Deteniendo…", "Stopping…"))

    def closeEvent(self, e):
        if self.running():
            self.proc.kill()
        super().closeEvent(e)

    def _reset_button(self):
        self.b_toggle.setEnabled(True)
        self.b_toggle.setText(tr("▶ Iniciar", "▶ Start"))
        self.b_toggle.setObjectName("accent")
        self.b_toggle.style().unpolish(self.b_toggle)
        self.b_toggle.style().polish(self.b_toggle)

    def _on_finished(self, *_):
        self._reset_button()
        self._flush()
        self._update_status()

    def _on_error(self, err):
        if err == QProcess.ProcessError.FailedToStart:
            self._reset_button()
            self.status.setText(tr("No se pudo ejecutar idevicesyslog (instala libimobiledevice-utils).",
                                   "Could not run idevicesyslog (install libimobiledevice-utils)."))

    def _on_out(self):
        self._buf += bytes(self.proc.readAllStandardOutput())
        *lines, self._buf = self._buf.split(b"\n")
        for ln in lines:
            txt = ANSI.sub("", ln.decode("utf-8", "replace")).rstrip("\r")
            if txt:
                self._pending.append(txt)
        if len(self._pending) > MAX_PENDING:
            over = len(self._pending) - MAX_PENDING // 2
            del self._pending[:over]
            self._dropped += over

    def _flush(self):
        if not self._pending:
            return
        chunk, self._pending = self._pending[:BATCH], self._pending[BATCH:]
        self.model.append([parse_line(x) for x in chunk])
        if self.chk_follow.isChecked():
            self.view.scrollToBottom()
        self._update_status()

    def _update_status(self):
        state = tr("● En vivo", "● Live") if self.running() else tr("■ Detenido", "■ Stopped")
        extra = tr(f" · {self._dropped} líneas omitidas por exceso", f" · {self._dropped} lines skipped (too many)") if self._dropped else ""
        self.status.setText(tr(f"{state} — {len(self.model.rows)} líneas ({self.proxy.rowCount()} visibles){extra}",
                               f"{state} — {len(self.model.rows)} lines ({self.proxy.rowCount()} visible){extra}"))

    def _refilter(self):
        self.proxy.text = self.filter.text().strip().lower()
        self.proxy.level = "" if self.level.currentIndex() == 0 else self.level.currentText()
        self.proxy.invalidateFilter()
        self._update_status()

    def _clear(self):
        self._pending.clear()
        self._dropped = 0
        self.model.clear()
        self._update_status()

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, tr("Guardar log", "Save log"), "syslog.txt", tr("Texto (*.txt)", "Text (*.txt)"))
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                for i in range(self.proxy.rowCount()):
                    fh.write(self.model.rows[self.proxy.mapToSource(self.proxy.index(i, 0)).row()][4] + "\n")
            self.status.setText(tr(f"Guardado en {path}", f"Saved to {path}"))

    def _terminal(self):
        udid = self.monitor.state.get("udid")
        open_terminal_or_warn(self, ["idevicesyslog"] + (["-u", udid] if udid else []))

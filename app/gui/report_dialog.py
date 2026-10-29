import os
import re

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

from ..core import device, infomap, report
from ..dispatch import run_async
from .. import privacy
from ..i18n import tr

CHECKABLE = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class ReportDialog(QDialog):
    def __init__(self, monitor, parent=None):
        super().__init__(parent)
        self.monitor = monitor
        self.fields = []
        self.setWindowTitle(tr("Informe PDF del dispositivo", "Device PDF report"))
        self.resize(980, 680)
        self.cfg = QSettings()

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([tr("Qué incluir en el PDF", "What to include in the PDF"), tr("Valor", "Value"),
                                   tr("Clave técnica", "Technical key")])
        self.tree.header().resizeSection(0, 280)
        self.tree.header().resizeSection(1, 260)
        b_all = QPushButton(tr("Marcar todo", "Select all"))
        b_none = QPushButton(tr("Desmarcar todo", "Select none"))
        b_rec = QPushButton(tr("Recomendado", "Recommended"))
        b_all.clicked.connect(lambda: self._set_all(True))
        b_none.clicked.connect(lambda: self._set_all(False))
        b_rec.clicked.connect(self._recommended)
        brow = QHBoxLayout()
        for b in (b_all, b_none, b_rec):
            brow.addWidget(b)
        brow.addStretch(1)
        self.status = QLabel(tr("Leyendo el dispositivo…", "Reading the device…"))

        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(tr("Notas y observaciones…", "Notes and remarks…"))
        self.notes.setFixedHeight(110)
        self.logo = QLineEdit(self.cfg.value("report/logo", ""))
        b_logo = QPushButton("…")
        b_logo.setFixedWidth(36)
        b_logo.clicked.connect(self._pick_logo)
        logo_row = QHBoxLayout()
        logo_row.addWidget(self.logo, 1)
        logo_row.addWidget(b_logo)
        self.chk_apps = QCheckBox(tr("Incluir lista de aplicaciones instaladas", "Include the list of installed apps"))
        self.chk_keys = QCheckBox(tr("Mostrar la clave técnica bajo cada campo", "Show the technical key under each field"))
        form = QFormLayout()
        form.addRow(tr("Logo (opcional):", "Logo (optional):"), logo_row)
        form.addRow(tr("Observaciones:", "Notes:"), self.notes)
        form.addRow("", self.chk_apps)
        form.addRow("", self.chk_keys)

        self.b_save = QPushButton(tr("Guardar PDF…", "Save PDF…"))
        self.b_save.setObjectName("accent")
        self.b_save.setEnabled(False)
        b_close = QPushButton(tr("Cerrar", "Close"))
        self.b_save.clicked.connect(self.generate)
        b_close.clicked.connect(self.close)
        bot = QHBoxLayout()
        bot.addStretch(1)
        bot.addWidget(b_close)
        bot.addWidget(self.b_save)

        left = QVBoxLayout()
        left.addLayout(brow)
        left.addWidget(self.tree, 1)
        left.addWidget(self.status)
        main = QHBoxLayout()
        main.addLayout(left, 3)
        right = QVBoxLayout()
        right.addLayout(form)
        right.addStretch(1)
        main.addLayout(right, 2)
        lay = QVBoxLayout(self)
        lay.addLayout(main, 1)
        lay.addLayout(bot)
        self.load()

    def load(self):
        s = self.monitor.state
        if s["mode"] == "normal" and s.get("info"):
            udid = s["udid"]
            run_async(lambda: device.get_full(udid), lambda res: self._fill(infomap.flatten(*res)),
                      lambda e: self.status.setText(tr(f"Error leyendo el dispositivo: {e}", f"Error reading the device: {e}")))
        elif s["mode"] == "recovery":
            self._fill(infomap.from_recovery(s["recovery"]))
        else:
            self.status.setText(tr("No hay ningún dispositivo listo. Conéctalo y confía en este equipo.",
                                   "No device is ready. Connect it and trust this computer."))

    def _default_checked(self, f):
        seen = set(self.cfg.value("report/seen", []) or [])
        checked = set(self.cfg.value("report/checked", []) or [])
        if f.key in seen:
            return f.key in checked
        return f.category not in infomap.DEFAULT_OFF_CATEGORIES

    def _fill(self, fields):
        self.fields = fields
        self.tree.clear()
        for cat, fs in infomap.group(fields):
            top = QTreeWidgetItem([infomap.category_label(cat)])
            top.setFlags(CHECKABLE | Qt.ItemFlag.ItemIsAutoTristate)
            fnt = top.font(0)
            fnt.setBold(True)
            top.setFont(0, fnt)
            self.tree.addTopLevelItem(top)
            for f in fs:
                ch = QTreeWidgetItem([f.label, f.value, f.key])
                ch.setFlags(CHECKABLE)
                ch.setData(0, Qt.ItemDataRole.UserRole, f.key)
                ch.setCheckState(0, Qt.CheckState.Checked if self._default_checked(f) else Qt.CheckState.Unchecked)
                top.addChild(ch)
            top.setExpanded(cat != "other")
        self.status.setText(tr(f"{len(fields)} datos disponibles. Marca los que quieres que salgan en el PDF.",
                               f"{len(fields)} items available. Tick the ones you want in the PDF."))
        self.b_save.setEnabled(True)

    def _children(self):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                yield top.child(j)

    def _set_all(self, on):
        st = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        for ch in self._children():
            ch.setCheckState(0, st)

    def _recommended(self):
        by_key = {f.key: f for f in self.fields}
        for ch in self._children():
            f = by_key[ch.data(0, Qt.ItemDataRole.UserRole)]
            ok = f.category not in infomap.DEFAULT_OFF_CATEGORIES
            ch.setCheckState(0, Qt.CheckState.Checked if ok else Qt.CheckState.Unchecked)

    def selected_groups(self):
        by_key = {f.key: f for f in self.fields}
        keys = {ch.data(0, Qt.ItemDataRole.UserRole) for ch in self._children()
                if ch.checkState(0) == Qt.CheckState.Checked}
        return infomap.group([f for f in self.fields if f.key in keys]), keys, set(by_key)

    def _pick_logo(self):
        f, _ = QFileDialog.getOpenFileName(self, "Logo", "", tr("Imágenes (*.png *.jpg *.jpeg *.svg)", "Images (*.png *.jpg *.jpeg *.svg)"))
        if f:
            self.logo.setText(f)

    def _default_name(self):
        by = {f.key: f.value for f in self.fields}
        model = by.get("ProductType") or by.get("PRODUCT") or tr("dispositivo", "device")
        serial = "" if privacy.enabled() else (by.get("SerialNumber") or by.get("SRNM") or "")
        return re.sub(r"[^\w.-]+", "_", f"{tr('Informe', 'Report')}_{model}_{serial}".strip("_")) + ".pdf"

    def generate(self):
        groups, keys, seen = self.selected_groups()
        if not groups:
            QMessageBox.information(self, tr("Informe", "Report"), tr("No hay ningún dato marcado.", "Nothing is ticked."))
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("Guardar informe", "Save report"),
                                              os.path.join(os.path.expanduser("~"), self._default_name()),
                                              "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        self.cfg.setValue("report/seen", sorted(seen))
        self.cfg.setValue("report/checked", sorted(keys))
        self.cfg.setValue("report/logo", self.logo.text())
        meta = {"notes": self.notes.toPlainText(),
                "logo": self.logo.text().strip() if os.path.isfile(self.logo.text().strip()) else ""}
        show_keys = self.chk_keys.isChecked()
        self.b_save.setEnabled(False)
        self.status.setText(tr("Generando PDF…", "Generating PDF…"))

        def finish(apps):
            try:
                report.write_pdf(path, report.build_html(meta, groups, apps, show_keys))
            except Exception as e:
                self.status.setText(tr(f"Error generando el PDF: {e}", f"Error generating the PDF: {e}"))
                self.b_save.setEnabled(True)
                return
            self.b_save.setEnabled(True)
            self.status.setText(tr(f"✅ Guardado: {path}", f"✅ Saved: {path}"))
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

        s = self.monitor.state
        if self.chk_apps.isChecked() and s["mode"] == "normal" and s.get("udid"):
            udid = s["udid"]
            from .viewers import AppsWindow
            run_async(lambda: AppsWindow.normalize(device.list_apps(udid)), finish,
                      lambda e: (self.status.setText(tr(f"No pude leer las apps ({e}); se genera sin ellas.",
                                                         f"Could not read the apps ({e}); generating without them.")), finish(None)))
        else:
            finish(None)

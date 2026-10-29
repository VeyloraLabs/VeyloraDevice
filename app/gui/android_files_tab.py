import posixpath
import tempfile
from pathlib import Path

from PySide6.QtCore import QPoint, QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QTableWidgetItem)
from qfluentwidgets import (Action, CaptionLabel, CommandBar, FluentIcon as FIF, LineEdit, MessageBoxBase, RoundMenu,
                            SubtitleLabel, TableWidget, ToolButton, TransparentPushButton)

from .. import i18n, theme
from ..core import android
from ..core.util import fmt_bytes
from ..dispatch import run_async
from ..i18n import tr
from .android_base import AndroidPage, confirm, relayout_bar, set_action_text, short_error
from .components import card_frame, toast

PLACES = (("Almacenamiento", "Storage", "/sdcard"), ("Descargas", "Downloads", "/sdcard/Download"),
          ("Cámara", "Camera", "/sdcard/DCIM"), ("Imágenes", "Pictures", "/sdcard/Pictures"),
          ("Documentos", "Documents", "/sdcard/Documents"), ("Música", "Music", "/sdcard/Music"))
OPEN_LIMIT = 50 * 1000 * 1000


class NameDialog(MessageBoxBase):

    def __init__(self, title, text, value="", parent=None, ok=None):
        super().__init__(parent)
        self.viewLayout.addWidget(SubtitleLabel(title))
        label = CaptionLabel(text)
        label.setStyleSheet(f"color:{theme.MUTED}")
        label.setWordWrap(True)
        self.viewLayout.addWidget(label)
        self.edit = LineEdit()
        self.edit.setText(value)
        self.edit.setClearButtonEnabled(True)
        self.edit.returnPressed.connect(self.yesButton.click)
        self.viewLayout.addWidget(self.edit)
        self.yesButton.setText(ok or tr("Aceptar", "OK"))
        self.cancelButton.setText(tr("Cancelar", "Cancel"))
        self.widget.setMinimumWidth(380)
        self.edit.setFocus()
        self.edit.selectAll()

    def validate(self):
        name = self.edit.text().strip()
        return bool(name) and "/" not in name


def ask_name(parent, title, text, value="", ok=None):
    dialog = NameDialog(title, text, value, parent.window(), ok)
    if dialog.exec():
        return dialog.edit.text().strip()
    return None


class AndroidFilesTab(AndroidPage):

    def __init__(self, monitor, parent=None):
        super().__init__("android-files", ("Archivos", "Files"),
                         ("Explora el almacenamiento del móvil. Arrastra archivos aquí para subirlos.",
                          "Browse the phone's storage. Drag files here to upload them."),
                         monitor, parent=parent)
        self.setAcceptDrops(True)
        self._path = "/sdcard"
        self._entries = []
        self._back = []
        self._forward = []
        self._loading = False
        self._error = ""

        nav = QHBoxLayout()
        nav.setSpacing(6)
        self.b_back = ToolButton(FIF.LEFT_ARROW)
        self.b_forward = ToolButton(FIF.RIGHT_ARROW)
        self.b_up = ToolButton(FIF.UP)
        self.b_refresh = ToolButton(FIF.SYNC)
        for button, handler in ((self.b_back, self._go_back), (self.b_forward, self._go_forward),
                                (self.b_up, self._go_up), (self.b_refresh, self._refresh)):
            button.clicked.connect(handler)
        self.path_edit = LineEdit()
        self.path_edit.setClearButtonEnabled(False)
        self.path_edit.returnPressed.connect(lambda: self.navigate(self.path_edit.text()))
        for button in (self.b_back, self.b_forward, self.b_up):
            nav.addWidget(button)
        nav.addWidget(self.path_edit, 1)
        nav.addWidget(self.b_refresh)
        self.content_layout.addLayout(nav)

        places = QHBoxLayout()
        places.setSpacing(4)
        self._place_buttons = []
        for es, en, path in PLACES:
            button = TransparentPushButton(FIF.FOLDER, "")
            button.clicked.connect(lambda _=False, p=path: self.navigate(p))
            places.addWidget(button)
            self._place_buttons.append((button, es, en))
        places.addStretch(1)
        self.content_layout.addLayout(places)

        self.commands = CommandBar()
        self.commands.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.a_upload_files = Action(FIF.UP, tr("Subir archivos", "Upload files"),
                                     triggered=lambda: self._upload_pick(False))
        self.a_upload_folder = Action(FIF.FOLDER_ADD, tr("Subir carpeta", "Upload folder"),
                                      triggered=lambda: self._upload_pick(True))
        self.a_download = Action(FIF.DOWNLOAD, tr("Descargar", "Download"), triggered=self._download)
        self.a_new = Action(FIF.ADD, tr("Carpeta nueva", "New folder"), triggered=self._new_folder)
        self.a_rename = Action(FIF.EDIT, tr("Renombrar", "Rename"), triggered=self._rename)
        self.a_delete = Action(FIF.DELETE, tr("Eliminar", "Delete"), triggered=self._delete)
        self.commands.addActions([self.a_upload_files, self.a_upload_folder, self.a_download])
        self.commands.addSeparator()
        self.commands.addActions([self.a_new, self.a_rename, self.a_delete])
        self.content_layout.addWidget(self.commands)

        card, cl = card_frame(margins=(10, 10, 10, 8), spacing=6)
        self.table = TableWidget()
        self.table.setColumnCount(3)
        self.table.setBorderVisible(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.table.cellDoubleClicked.connect(lambda row, _c: self._open_row(row))
        self.empty = CaptionLabel("")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet(f"color:{theme.MUTED}")
        self.count = CaptionLabel("")
        self.count.setStyleSheet(f"color:{theme.MUTED}")
        cl.addWidget(self.table, 1)
        cl.addWidget(self.empty, 1)
        cl.addWidget(self.count)
        self.content_layout.addWidget(card, 1)

        for sequence, handler in (("Alt+Left", self._go_back), ("Alt+Right", self._go_forward),
                                  ("Alt+Up", self._go_up), ("Backspace", self._go_up), ("Delete", self._delete),
                                  ("F2", self._rename), ("Ctrl+Shift+N", self._new_folder),
                                  ("Ctrl+L", lambda: self.path_edit.setFocus())):
            QShortcut(QKeySequence(sequence), self, activated=handler).setContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut)

        i18n.on_change(lambda _c: self._retranslate())
        self._retranslate()
        self.finish_setup()

    def _retranslate(self):
        for button, es, en in self._place_buttons:
            button.setText(tr(es, en))
        for action, es, en in ((self.a_upload_files, "Subir archivos", "Upload files"),
                               (self.a_upload_folder, "Subir carpeta", "Upload folder"),
                               (self.a_download, "Descargar", "Download"), (self.a_new, "Carpeta nueva", "New folder"),
                               (self.a_rename, "Renombrar", "Rename"), (self.a_delete, "Eliminar", "Delete")):
            set_action_text(action, es, en)
        relayout_bar(self.commands)
        self.table.setHorizontalHeaderLabels([tr("Nombre", "Name"), tr("Tamaño", "Size"), tr("Modificado", "Modified")])
        self.b_back.setToolTip(tr("Atrás (Alt+←)", "Back (Alt+←)"))
        self.b_forward.setToolTip(tr("Adelante (Alt+→)", "Forward (Alt+→)"))
        self.b_up.setToolTip(tr("Carpeta superior (Alt+↑)", "Parent folder (Alt+↑)"))
        self.b_refresh.setToolTip(tr("Actualizar (F5)", "Refresh (F5)"))
        self._fill()

    def on_device_changed(self):
        self._entries = []
        self._back.clear()
        self._forward.clear()
        self._error = ""
        self._loading = False
        self._path = "/sdcard"
        self._fill()

    def load(self):
        self._list(self._path)

    def navigate(self, path):
        if not self.ready:
            return
        path = android.clean_path(path)
        if path == self._path:
            self._refresh()
            return

        def remember(previous):
            self._back.append(previous)
            self._forward.clear()

        self._list(path, remember)

    def _list(self, path, on_ok=None):
        serial = self.serial
        self._loading = True
        self._error = ""
        self._gen += 1
        self._fill()

        def loaded(entries):
            self._loading = False
            previous, self._path = self._path, path
            self._entries = entries
            if on_ok:
                on_ok(previous)
            self._fill()

        def failed(error):
            self._loading = False
            self._error = str(error)
            self._fill()
            toast(self, "err", tr("No se puede abrir la carpeta", "Cannot open the folder"), short_error(error), 6000)

        run_async(lambda: android.list_dir(serial, path), self.guard(loaded), self.guard(failed))

    def _refresh(self):
        if self.ready:
            self._list(self._path)

    def _go_back(self):
        if self._back and self.ready:
            def moved(previous):
                self._back.pop()
                self._forward.append(previous)

            self._list(self._back[-1], moved)

    def _go_forward(self):
        if self._forward and self.ready:
            def moved(previous):
                self._forward.pop()
                self._back.append(previous)

            self._list(self._forward[-1], moved)

    def _go_up(self):
        if self.ready and self._path != "/":
            self.navigate(posixpath.dirname(self._path) or "/")

    def _fill(self):
        self.path_edit.setText(self._path)
        entries = self._entries
        self.table.blockSignals(True)
        self.table.setRowCount(len(entries))
        for index, entry in enumerate(entries):
            name = QTableWidgetItem(entry["name"] + ("/" if entry["is_dir"] else ""))
            name.setIcon((FIF.FOLDER if entry["is_dir"] else FIF.DOCUMENT).icon())
            size = QTableWidgetItem("" if entry["is_dir"] else fmt_bytes(entry["size"]))
            size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(index, 0, name)
            self.table.setItem(index, 1, size)
            self.table.setItem(index, 2, QTableWidgetItem(entry["modified"]))
        self.table.blockSignals(False)
        self.table.setVisible(bool(entries))
        self.empty.setVisible(not entries)
        if self._loading:
            self.empty.setText(tr("Leyendo la carpeta…", "Reading the folder…"))
        elif self._error:
            self.empty.setText(self._error)
        else:
            self.empty.setText(tr("Esta carpeta está vacía.", "This folder is empty."))
        folders = sum(1 for e in entries if e["is_dir"])
        self.count.setText(tr(f"{folders} carpetas · {len(entries) - folders} archivos",
                              f"{folders} folders · {len(entries) - folders} files"))
        self.update_actions()

    def _selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._entries[r] for r in rows if r < len(self._entries)]

    def _full(self, entry):
        return posixpath.join(self._path, entry["name"])

    def update_actions(self):
        if not hasattr(self, "a_delete"):
            return
        act = self.can_act()
        selected = self._selected() if hasattr(self, "table") else []
        self.b_back.setEnabled(act and bool(self._back))
        self.b_forward.setEnabled(act and bool(self._forward))
        self.b_up.setEnabled(act and self._path != "/")
        self.b_refresh.setEnabled(act)
        self.path_edit.setEnabled(act)
        for button, _es, _en in self._place_buttons:
            button.setEnabled(act)
        self.a_upload_files.setEnabled(act)
        self.a_upload_folder.setEnabled(act)
        self.a_new.setEnabled(act)
        self.a_download.setEnabled(act and bool(selected))
        self.a_rename.setEnabled(act and len(selected) == 1)
        self.a_delete.setEnabled(act and bool(selected))

    def _open_row(self, row):
        if not 0 <= row < len(self._entries) or not self.can_act():
            return
        entry = self._entries[row]
        if entry["is_dir"]:
            self.navigate(self._full(entry))
            return
        if entry["size"] > OPEN_LIMIT:
            toast(self, "warn", tr("Archivo grande", "Large file"),
                  tr("Pesa más de 50 MB: usa «Descargar» y ábrelo desde tu carpeta.",
                     "It is over 50 MB: use “Download” and open it from your folder."), 6000)
            return
        serial, remote = self.serial, self._full(entry)
        target = Path(tempfile.mkdtemp(prefix="veyloradevice-"))

        def done(_r):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target / entry["name"])))

        self.run_task(lambda: android.pull_path(serial, remote, target), done=done,
                      err_title=tr("No se pudo abrir", "Could not open"))

    def _context_menu(self, pos):
        menu = RoundMenu(parent=self)
        selected = self._selected()
        if selected:
            for action in (self.a_download, self.a_rename, self.a_delete):
                if action.isEnabled():
                    menu.addAction(Action(action.icon(), action.text(), triggered=action.trigger))
            menu.addSeparator()
            menu.addAction(Action(FIF.COPY, tr("Copiar ruta", "Copy path"), triggered=lambda: QGuiApplication
                                  .clipboard().setText("\n".join(self._full(e) for e in selected))))
        for action in (self.a_upload_files, self.a_new):
            if action.isEnabled():
                menu.addAction(Action(action.icon(), action.text(), triggered=action.trigger))
        menu.exec(self.table.viewport().mapToGlobal(QPoint(pos.x(), pos.y())))

    @staticmethod
    def _last_dir(key, default):
        return str(QSettings().value(key, default))

    def _download(self):
        selected = self._selected()
        if not selected or not self.can_act():
            return
        folder = QFileDialog.getExistingDirectory(self, tr("Guardar en…", "Save to…"),
                                                  self._last_dir("android_files_dl", str(Path.home() / "Downloads")))
        if not folder:
            return
        QSettings().setValue("android_files_dl", folder)
        serial = self.serial
        remotes = [self._full(e) for e in selected]

        def work():
            for remote in remotes:
                android.pull_path(serial, remote, folder)

        self.run_task(work, ok_title=tr("Descarga completada", "Download complete"),
                      ok_text=tr(f"{len(remotes)} elementos en {folder}", f"{len(remotes)} items in {folder}"),
                      err_title=tr("No se pudo descargar", "Could not download"))

    def _upload_pick(self, folder):
        if not self.can_act():
            return
        start = self._last_dir("android_files_ul", str(Path.home()))
        if folder:
            path = QFileDialog.getExistingDirectory(self, tr("Carpeta que subir", "Folder to upload"), start)
            paths = [path] if path else []
        else:
            paths, _ = QFileDialog.getOpenFileNames(self, tr("Archivos que subir", "Files to upload"), start)
        if paths:
            QSettings().setValue("android_files_ul", str(Path(paths[0]).parent))
            self.upload(paths)

    def upload(self, paths):
        if not self.can_act() or not paths:
            return
        names = {e["name"] for e in self._entries}
        clashes = [Path(p).name for p in paths if Path(p).name in names]
        if clashes and not confirm(
                self, tr("Reemplazar archivos", "Replace files"),
                tr("Ya existen en esta carpeta del móvil:\n", "These already exist in this phone folder:\n")
                + "\n".join(f"• {n}" for n in clashes[:8]) + ("\n…" if len(clashes) > 8 else "")
                + "\n\n" + tr("Se reemplazarán por los nuevos.", "They will be replaced by the new ones."),
                ok=tr("Reemplazar", "Replace"), danger=True):
            return
        serial, destination = self.serial, self._path

        def work():
            for path in paths:
                android.push_path(serial, path, destination)

        self.run_task(work, done=lambda _r: self._refresh(), ok_title=tr("Subida completada", "Upload complete"),
                      ok_text=tr(f"{len(paths)} elementos en {destination}", f"{len(paths)} items in {destination}"),
                      err_title=tr("No se pudo subir", "Could not upload"))

    def _new_folder(self):
        if not self.can_act():
            return
        name = ask_name(self, tr("Carpeta nueva", "New folder"),
                        tr(f"Se creará dentro de {self._path}", f"It will be created inside {self._path}"),
                        ok=tr("Crear", "Create"))
        if not name:
            return
        serial, path = self.serial, posixpath.join(self._path, name)
        self.run_task(lambda: android.make_dir(serial, path), done=lambda _r: self._refresh())

    def _rename(self):
        selected = self._selected()
        if len(selected) != 1 or not self.can_act():
            return
        entry = selected[0]
        name = ask_name(self, tr("Renombrar", "Rename"), self._full(entry), entry["name"], ok=tr("Renombrar", "Rename"))
        if not name or name == entry["name"]:
            return
        serial, path = self.serial, self._full(entry)
        self.run_task(lambda: android.rename_path(serial, path, name), done=lambda _r: self._refresh())

    def _delete(self):
        selected = self._selected()
        if not selected or not self.can_act():
            return
        names = "\n".join(f"• {e['name']}{'/' if e['is_dir'] else ''}" for e in selected[:8])
        if len(selected) > 8:
            names += "\n…"
        if not confirm(self, tr("Eliminar del móvil", "Delete from phone"),
                       tr(f"Se eliminará de forma permanente (no hay papelera):\n{names}",
                          f"This will be deleted permanently (there is no recycle bin):\n{names}"),
                       ok=tr("Eliminar", "Delete"), danger=True):
            return
        serial = self.serial
        paths = [self._full(e) for e in selected]

        def work():
            for path in paths:
                android.delete_path(serial, path)

        self.run_task(work, done=lambda _r: self._refresh(), fail=lambda _e: self._refresh(),
                      err_title=tr("No se pudo eliminar", "Could not delete"))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self.can_act():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.upload(paths)

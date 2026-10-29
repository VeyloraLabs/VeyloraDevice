from pathlib import Path

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView,
                               QTableWidgetItem)
from qfluentwidgets import (Action, CaptionLabel, CommandBar, FluentIcon as FIF, PrimarySplitPushButton, RoundMenu,
                            SearchLineEdit, SegmentedWidget, StrongBodyLabel, TableWidget)

from .. import i18n, theme
from ..core import android
from ..dispatch import run_async
from ..i18n import tr
from .android_base import AndroidPage, confirm, relayout_bar, set_action_text, short_error
from .android_dialogs import run_batch
from .components import card_frame, toast

FILTERS = (("user", "Usuario", "User"), ("system", "Sistema", "System"), ("disabled", "Desactivadas", "Disabled"),
           ("removed", "Quitadas", "Removed"), ("all", "Todas", "All"))

DETAIL_FIELDS = (("version_name", "Versión", "Version"), ("version_code", "Código de versión", "Version code"),
                 ("first_install", "Instalada", "Installed"), ("last_update", "Actualizada", "Updated"),
                 ("target_sdk", "SDK objetivo", "Target SDK"), ("min_sdk", "SDK mínimo", "Minimum SDK"),
                 ("installer", "Instalada desde", "Installed from"), ("data_dir", "Carpeta de datos", "Data folder"))


def expand_apk_paths(paths):
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found += sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() == ".apk")
        elif path.is_file() and path.suffix.lower() == ".apk":
            found.append(path)
    return [str(p) for p in dict.fromkeys(found)]


def app_matches(app, key, query):
    if key == "user" and app["system"]:
        return False
    if key == "system" and not app["system"]:
        return False
    if key == "disabled" and not app["disabled"]:
        return False
    if key == "removed" and not app["removed"]:
        return False
    if key != "removed" and key != "all" and app["removed"]:
        return False
    return not query or query in app["package"].lower()


class AndroidAppsTab(AndroidPage):

    def __init__(self, monitor, parent=None):
        super().__init__("android-apps", ("Aplicaciones", "Apps"),
                         ("Instala, abre, desactiva o desinstala las apps del móvil. También puedes arrastrar APK aquí.",
                          "Install, open, disable or uninstall the phone's apps. You can also drag APK files here."),
                         monitor, parent=parent)
        self.setAcceptDrops(True)
        self._apps = []
        self._shown = []
        self._details = {}
        self._detail_package = None
        self._filter = "user"
        self._loading = False

        self.bar = CommandBar()
        self.bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.b_refresh = self._act(FIF.SYNC, "Actualizar", "Refresh", self.reload)
        self.b_select = self._act(getattr(FIF, "CHECKBOX", FIF.ACCEPT), "Seleccionar todo", "Select all",
                                  lambda: self.table.selectAll())
        self.bar.addSeparator()
        self.b_open = self._act(FIF.PLAY, "Abrir", "Open", self._open)
        self.b_stop = self._act(FIF.CLOSE, "Detener", "Stop", self._stop)
        self.b_settings = self._act(FIF.SETTING, "Ajustes", "Settings", self._settings)
        self.bar.addSeparator()
        self.b_clear = self._act(FIF.BROOM, "Borrar datos", "Clear data", self._clear)
        self.b_toggle = self._act(FIF.HIDE, "Desactivar", "Disable", self._toggle)
        self.b_extract = self._act(FIF.DOWNLOAD, "Extraer APK", "Extract APK", self._extract)
        self.b_remove = self._act(FIF.DELETE, "Desinstalar", "Uninstall", self._remove)
        self.content_layout.addWidget(self.bar)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.search = SearchLineEdit()
        i18n.bind(self.search, "setPlaceholderText", "Buscar por nombre de paquete…", "Search by package name…")
        self.search.textChanged.connect(lambda _t: self._fill())
        top.addWidget(self.search, 1)
        self.install_button = PrimarySplitPushButton(self)
        self.install_button.setIcon(FIF.ADD)
        self.install_button.clicked.connect(lambda: self._pick_apks(False))
        menu = RoundMenu(parent=self)
        self._install_actions = (
            Action(FIF.ADD, "", triggered=lambda: self._pick_apks(False)),
            Action(FIF.FOLDER_ADD, "", triggered=lambda: self._pick_apks(True)),
            Action(FIF.FOLDER, "", triggered=self._pick_folder),
        )
        for action in self._install_actions:
            menu.addAction(action)
        self.install_button.setFlyout(menu)
        top.addWidget(self.install_button)
        self.content_layout.addLayout(top)
        self.segments = SegmentedWidget()
        for key, es, en in FILTERS:
            self.segments.addItem(key, tr(es, en), onClick=lambda _=False, k=key: self._set_filter(k))
        self.segments.setCurrentItem(self._filter)
        filters = QHBoxLayout()
        filters.addWidget(self.segments)
        filters.addStretch(1)
        self.content_layout.addLayout(filters)

        row = QHBoxLayout()
        row.setSpacing(12)
        list_card, list_layout = card_frame(margins=(10, 10, 10, 8), spacing=6)
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
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(lambda *_: self._open())
        self.empty = CaptionLabel("")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet(f"color:{theme.MUTED}")
        self.count = CaptionLabel("")
        self.count.setStyleSheet(f"color:{theme.MUTED}")
        list_layout.addWidget(self.table, 1)
        list_layout.addWidget(self.empty, 1)
        list_layout.addWidget(self.count)
        row.addWidget(list_card, 6)

        detail_card, dl = card_frame(margins=(16, 14, 16, 14), spacing=8)
        detail_card.setMinimumWidth(300)
        detail_card.setMaximumWidth(400)
        self.d_title = StrongBodyLabel("")
        self.d_title.setWordWrap(True)
        self.d_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.d_sub = CaptionLabel("")
        self.d_sub.setStyleSheet(f"color:{theme.MUTED}")
        self.d_sub.setWordWrap(True)
        dl.addWidget(self.d_title)
        dl.addWidget(self.d_sub)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        self._detail_labels = {}
        for index, (key, es, en) in enumerate(DETAIL_FIELDS):
            name = i18n.bind(CaptionLabel(), "setText", es, en)
            name.setStyleSheet(f"color:{theme.MUTED}")
            value = CaptionLabel("")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(name, index, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value, index, 1)
            self._detail_labels[key] = (name, value)
        grid.setColumnStretch(1, 1)
        dl.addLayout(grid)
        dl.addStretch(1)

        row.addWidget(detail_card, 4)
        self.content_layout.addLayout(row, 1)

        for sequence, handler in (("Ctrl+F", lambda: self.search.setFocus()), ("Ctrl+I", lambda: self._pick_apks(False)),
                                  ("Delete", self._remove)):
            QShortcut(QKeySequence(sequence), self, activated=handler).setContext(
                Qt.ShortcutContext.WidgetWithChildrenShortcut)

        i18n.on_change(lambda _c: self._retranslate())
        self._retranslate()
        self.finish_setup()

    def _act(self, icon, es, en, fn):
        action = Action(icon, tr(es, en))
        action._es_en = (es, en)
        action.triggered.connect(lambda *_: fn())
        self.bar.addAction(action)
        return action

    def _retranslate(self):
        self.install_button.setText(tr("Instalar APK…", "Install APK…"))
        self._install_actions[0].setText(tr("Instalar APK…", "Install APK…"))
        self._install_actions[1].setText(tr("Instalar app dividida (varios APK)…", "Install split app (several APKs)…"))
        self._install_actions[2].setText(tr("Instalar todos los APK de una carpeta…", "Install all APKs in a folder…"))
        self.table.setHorizontalHeaderLabels([tr("Paquete", "Package"), tr("Tipo", "Type"), tr("Estado", "State")])
        for key, es, en in FILTERS:
            item = self.segments.items.get(key)
            if item:
                item.setText(tr(es, en))
        self._fill()
        self._update_buttons()

    def on_device_changed(self):
        self._apps = []
        self._details.clear()
        self._detail_package = None
        self._loading = False
        self._fill()

    def load(self):
        serial = self.serial
        self._loading = True
        self._fill()
        run_async(lambda: android.list_packages(serial), self.guard(self._apps_loaded), self.guard(self._load_failed))

    def _apps_loaded(self, apps):
        self._loading = False
        self._apps = apps
        self._fill()

    def _load_failed(self, error):
        self._loading = False
        self._fill()
        toast(self, "err", tr("No se pudo leer la lista de apps", "Could not read the app list"), short_error(error), 7000)

    def _set_filter(self, key):
        self._filter = key
        self._fill()

    def _fill(self):
        selected = set(self._selected_packages())
        query = self.search.text().strip().lower()
        self._shown = [a for a in self._apps if app_matches(a, self._filter, query)]
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._shown))
        for index, app in enumerate(self._shown):
            state = (tr("Quitada", "Removed") if app["removed"] else tr("Desactivada", "Disabled")
                     if app["disabled"] else tr("Activa", "Enabled"))
            for column, text in enumerate((app["package"], tr("Sistema", "System") if app["system"]
                                           else tr("Usuario", "User"), state)):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if column == 2 and (app["disabled"] or app["removed"]):
                    item.setForeground(Qt.GlobalColor.yellow)
                self.table.setItem(index, column, item)
            if app["package"] in selected:
                self.table.selectRow(index)
        self.table.blockSignals(False)
        self.table.setVisible(bool(self._shown))
        self.empty.setVisible(not self._shown)
        if self._loading:
            self.empty.setText(tr("Leyendo las aplicaciones del móvil…", "Reading the phone's apps…"))
        elif not self._apps:
            self.empty.setText(tr("Aquí aparecerán las aplicaciones.", "Apps will appear here."))
        else:
            self.empty.setText(tr("Ninguna aplicación coincide con el filtro.", "No app matches the filter."))
        self.count.setText(tr(f"{len(self._shown)} de {len(self._apps)} aplicaciones",
                              f"{len(self._shown)} of {len(self._apps)} apps"))
        self._selection_changed()

    def _selected_packages(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self._shown[r]["package"] for r in rows if r < len(self._shown)]

    def _selected_apps(self):
        wanted = set(self._selected_packages())
        return [a for a in self._shown if a["package"] in wanted]

    def _selection_changed(self):
        apps = self._selected_apps()
        if len(apps) == 1:
            app = apps[0]
            self.d_title.setText(app["package"])
            kind = tr("App del sistema", "System app") if app["system"] else tr("App de usuario", "User app")
            self.d_sub.setText(kind + (" · " + tr("desactivada", "disabled") if app["disabled"] else "")
                               + (" · " + tr("quitada", "removed") if app["removed"] else ""))
            self._show_details(app)
        elif apps:
            self.d_title.setText(tr(f"{len(apps)} apps seleccionadas", f"{len(apps)} apps selected"))
            self.d_sub.setText(tr("Puedes extraer sus APK o desinstalarlas a la vez.",
                                  "You can extract their APKs or uninstall them together."))
            self._clear_details()
        else:
            self.d_title.setText(tr("Selecciona una app", "Select an app"))
            self.d_sub.setText(tr("Elige una de la lista para ver sus datos y acciones. Doble clic para abrirla.",
                                  "Pick one from the list to see its details and actions. Double-click to open it."))
            self._clear_details()
        self._update_buttons()

    def _clear_details(self):
        self._detail_package = None
        for name, value in self._detail_labels.values():
            name.setVisible(False)
            value.setVisible(False)
        for _name, value in self._detail_labels.values():
            value.setText("")

    def _show_details(self, app):
        for name, value in self._detail_labels.values():
            name.setVisible(True)
            value.setVisible(True)
        package = app["package"]
        self._detail_package = package
        cached = self._details.get(package)
        if cached is not None:
            self._paint_details(cached)
            return
        self._paint_details({})
        if app["removed"]:
            return
        serial = self.serial

        def loaded(details):
            self._details[package] = details
            if self._detail_package == package:
                self._paint_details(details)

        run_async(lambda: android.package_details(serial, package), self.guard(loaded), lambda _e: None)

    def _paint_details(self, details):
        for key, (_name, value) in self._detail_labels.items():
            value.setText(details.get(key, ""))

    def update_actions(self):
        self._update_buttons()

    def _update_buttons(self):
        if not hasattr(self, "b_open"):
            return
        apps = self._selected_apps()
        act = self.can_act()
        one = len(apps) == 1
        app = apps[0] if one else None
        live = bool(one and not app["removed"])
        self.install_button.setEnabled(act)
        changed = False
        for action in (self.b_refresh, self.b_select, self.b_open, self.b_stop, self.b_settings, self.b_clear,
                       self.b_extract):
            changed |= set_action_text(action, *action._es_en)
        changed |= set_action_text(self.b_toggle, *(("Activar", "Enable") if one and app["disabled"]
                                                    else ("Desactivar", "Disable")))
        if one and app["removed"]:
            changed |= set_action_text(self.b_remove, "Restaurar", "Restore")
        elif one and app["system"]:
            changed |= set_action_text(self.b_remove, "Quitar del móvil", "Remove from phone")
        else:
            changed |= set_action_text(self.b_remove, "Desinstalar", "Uninstall")
        if changed:
            relayout_bar(self.bar)
        self.b_select.setEnabled(act and bool(self._shown))
        removable = [a for a in apps if not a["removed"]]
        self.b_refresh.setEnabled(not self.busy)
        for button, enabled in ((self.b_open, live and not app["disabled"]), (self.b_stop, live),
                                (self.b_settings, live), (self.b_clear, live),
                                (self.b_toggle, live),
                                (self.b_extract, bool(removable)),
                                (self.b_remove, bool(apps) and (bool(removable) or one))):
            button.setEnabled(act and bool(enabled))

    def _context_menu(self, pos):
        if not self._selected_apps():
            return
        menu = RoundMenu(parent=self)
        for button, icon in ((self.b_open, FIF.PLAY), (self.b_stop, FIF.CLOSE), (self.b_settings, FIF.SETTING),
                             (self.b_clear, FIF.BROOM), (self.b_toggle, FIF.HIDE), (self.b_extract, FIF.DOWNLOAD),
                             (self.b_remove, FIF.DELETE)):
            if button.isEnabled():
                menu.addAction(Action(icon, button.text(), triggered=button.trigger))
        menu.addSeparator()
        menu.addAction(Action(FIF.COPY, tr("Copiar nombre del paquete", "Copy package name"),
                              triggered=lambda: QGuiApplication.clipboard().setText(
                                  "\n".join(self._selected_packages()))))
        menu.exec(self.table.viewport().mapToGlobal(QPoint(pos.x(), pos.y())))

    def _single(self):
        apps = self._selected_apps()
        return apps[0] if len(apps) == 1 and self.can_act() else None

    def _after(self, _result=None):
        self._details.clear()
        self.reload_list()

    def reload_list(self):
        if self.ready:
            self.load()

    def _open(self):
        app = self._single()
        if not app or app["removed"] or app["disabled"]:
            return
        serial, package = self.serial, app["package"]
        self.run_task(lambda: android.launch_app(serial, package), err_title=tr("No se pudo abrir", "Could not open"))

    def _stop(self):
        app = self._single()
        if not app:
            return
        serial, package = self.serial, app["package"]
        self.run_task(lambda: android.force_stop(serial, package), ok_title=tr("Detenida", "Stopped"),
                      ok_text=package)

    def _settings(self):
        app = self._single()
        if not app:
            return
        serial, package = self.serial, app["package"]
        self.run_task(lambda: android.open_app_settings(serial, package))

    def _clear(self):
        app = self._single()
        if not app:
            return
        if not confirm(self, tr("Borrar datos", "Clear data"),
                       tr(f"Se borrarán todos los datos de {app['package']}: cuentas, ajustes y archivos de la app. "
                          "No se puede deshacer.",
                          f"All data of {app['package']} will be erased: accounts, settings and the app's files. "
                          "This cannot be undone."),
                       ok=tr("Borrar datos", "Clear data"), danger=True):
            return
        serial, package = self.serial, app["package"]
        self.run_task(lambda: android.clear_data(serial, package), ok_title=tr("Datos borrados", "Data cleared"),
                      ok_text=package)

    def _toggle(self):
        app = self._single()
        if not app or app["removed"]:
            return
        serial, package = self.serial, app["package"]
        enable = app["disabled"]
        if not enable and not confirm(
                self, tr("Desactivar app", "Disable app"),
                tr(f"{package} dejará de funcionar y desaparecerá del menú de apps. Podrás volver a activarla desde aquí.",
                   f"{package} will stop working and disappear from the app menu. You can enable it again from here."),
                ok=tr("Desactivar", "Disable")):
            return
        self.run_task(lambda: android.set_enabled(serial, package, enable), done=self._after,
                      ok_title=tr("Hecho", "Done"),
                      ok_text=tr("App activada.", "App enabled.") if enable else tr("App desactivada.", "App disabled."))

    def _extract(self):
        apps = [a for a in self._selected_apps() if not a["removed"]]
        if not apps or not self.can_act():
            return
        folder = QFileDialog.getExistingDirectory(self, tr("Carpeta donde guardar los APK", "Folder to save the APKs"),
                                                  self._download_dir())
        if not folder:
            return
        QSettings().setValue("android_apk_dir", folder)
        serial = self.serial
        packages = [a["package"] for a in apps]
        if len(packages) == 1:
            self.run_task(lambda: android.extract_apk(serial, packages[0], folder),
                          ok_title=tr("APK extraído", "APK extracted"), ok_text=folder,
                          err_title=tr("No se pudo extraer", "Could not extract"))
            return
        results = run_batch(self, tr("Extrayendo APK", "Extracting APKs"), packages,
                            lambda package: android.extract_apk(serial, package, folder), lambda package: package)
        good = sum(1 for _p, error in results if error is None)
        toast(self, "ok" if good else "err", tr("APK extraídos", "APKs extracted"),
              tr(f"{good} de {len(packages)} en {folder}", f"{good} of {len(packages)} in {folder}"), 6000)

    @staticmethod
    def _download_dir():
        return str(QSettings().value("android_apk_dir", str(Path.home() / "Downloads")))

    def _remove(self):
        apps = self._selected_apps()
        if not apps or not self.can_act():
            return
        serial = self.serial
        if len(apps) == 1 and apps[0]["removed"]:
            package = apps[0]["package"]
            if not confirm(self, tr("Restaurar app", "Restore app"),
                           tr(f"Se volverá a instalar {package} desde la copia del sistema.",
                              f"{package} will be reinstalled from the system image."),
                           ok=tr("Restaurar", "Restore")):
                return
            self.run_task(lambda: android.restore_system_app(serial, package), done=self._after,
                          ok_title=tr("App restaurada", "App restored"), ok_text=package)
            return
        apps = [a for a in apps if not a["removed"]]
        if not apps:
            return
        system = [a for a in apps if a["system"]]
        if len(apps) == 1:
            name = apps[0]["package"]
            title = tr("Quitar app del sistema", "Remove system app") if system else tr("Desinstalar app", "Uninstall app")
        else:
            shown = "\n".join(f"• {a['package']}" for a in apps[:6]) + (
                tr(f"\n… y {len(apps) - 6} más", f"\n… and {len(apps) - 6} more") if len(apps) > 6 else "")
            name = tr(f"{len(apps)} apps:\n{shown}\n", f"{len(apps)} apps:\n{shown}\n")
            title = tr(f"Desinstalar {len(apps)} apps", f"Uninstall {len(apps)} apps")
        text = tr(f"Se va a desinstalar {name} y se perderán sus datos.",
                  f"{name} will be uninstalled and its data will be lost.")
        if system:
            text += "\n\n" + tr(f"{len(system)} son apps del sistema: no se borran de verdad, se quitan solo para tu "
                                  "usuario y puedes restaurarlas desde el filtro «Quitadas». Quitar apps importantes "
                                  "puede dejar el móvil inestable.",
                                  f"{len(system)} are system apps: they are not really deleted, only removed for your "
                                  "user, and can be restored from the “Removed” filter. Removing important apps can "
                                  "make the phone unstable.")
        if not confirm(self, title, text, ok=tr("Desinstalar", "Uninstall"), danger=True):
            return
        items = [(a["package"], a["system"]) for a in apps]
        if len(items) == 1:
            package, is_system = items[0]
            self.run_task(lambda: android.uninstall(serial, package, system=is_system), done=self._after,
                          fail=self._after, ok_title=tr("Desinstalada", "Uninstalled"), ok_text=package,
                          err_title=tr("No se pudo desinstalar", "Could not uninstall"))
            return
        results = run_batch(self, tr("Desinstalando apps", "Uninstalling apps"), items,
                            lambda item: android.uninstall(serial, item[0], system=item[1]), lambda item: item[0])
        good = sum(1 for _i, error in results if error is None)
        toast(self, "ok" if good else "err", tr("Desinstalación terminada", "Uninstall finished"),
              tr(f"{good} de {len(items)} desinstaladas.", f"{good} of {len(items)} uninstalled."), 6000)
        self._after()

    def _pick_apks(self, split):
        if not self.can_act():
            return
        title = tr("Elegir las partes de la app (APK)", "Choose the app parts (APKs)") if split \
            else tr("Elegir APK (puedes marcar varios)", "Choose APKs (you can select several)")
        paths, _ = QFileDialog.getOpenFileNames(self, title, self._download_dir(), "Android (*.apk)")
        if paths:
            self.install_files(paths, split)

    def _pick_folder(self):
        if not self.can_act():
            return
        folder = QFileDialog.getExistingDirectory(self, tr("Carpeta con los APK (incluye subcarpetas)",
                                                           "Folder with the APKs (includes subfolders)"),
                                                  self._download_dir())
        if not folder:
            return
        QSettings().setValue("android_apk_dir", folder)
        paths = expand_apk_paths([folder])
        if not paths:
            toast(self, "warn", tr("Sin APK", "No APKs"), tr("No hay ningún .apk en esa carpeta.",
                                                              "There is no .apk in that folder."))
            return
        if confirm(self, tr("Instalar todos los APK", "Install all the APKs"),
                   tr(f"Se instalarán {len(paths)} APK de la carpeta, uno detrás de otro. Si alguno falla se sigue con "
                      "el resto y al final verás cuáles fallaron.",
                      f"{len(paths)} APKs from the folder will be installed one after another. If one fails the rest "
                      "continue and you will see which ones failed at the end."),
                   ok=tr(f"Instalar {len(paths)}", f"Install {len(paths)}")):
            self.install_files(paths)

    def install_files(self, paths, split=False, downgrade=False):
        paths = expand_apk_paths(paths)
        if not paths or not self.can_act():
            return
        serial = self.serial
        groups = [paths] if split and len(paths) > 1 else [[p] for p in paths]
        if len(groups) > 1:
            results = run_batch(self, tr("Instalando apps", "Installing apps"), groups,
                                lambda group: android.install_apks(serial, group, downgrade=downgrade),
                                lambda group: Path(group[0]).name)
            good = sum(1 for _g, error in results if error is None)
            toast(self, "ok" if good else "err", tr("Instalación terminada", "Install finished"),
                  tr(f"{good} de {len(groups)} instaladas.", f"{good} of {len(groups)} installed."), 6000)
            self._after()
            return

        def work():
            results = []
            for group in groups:
                try:
                    android.install_apks(serial, group, downgrade=downgrade, split=split)
                    results.append((group, None))
                except android.InstallError as exc:
                    results.append((group, exc))
                except android.AndroidError as exc:
                    results.append((group, android.InstallError("", str(exc))))
            return results

        self.run_task(work, done=lambda results: self._installed(results, split, downgrade))

    def _installed(self, results, split, downgrade):
        failures = [(group, error) for group, error in results if error]
        good = len(results) - len(failures)
        if good:
            toast(self, "ok", tr("Instalación completada", "Installation complete"),
                  tr(f"{good} de {len(results)} correctas.", f"{good} of {len(results)} succeeded."))
            self._after()
        if not failures:
            return
        if len(failures) == 1:
            group, error = failures[0]
            if error.code == "INSTALL_FAILED_VERSION_DOWNGRADE" and not downgrade:
                if confirm(self, tr("Ya hay una versión más nueva", "A newer version is installed"),
                           tr(f"{Path(group[0]).name} es más antigua que la instalada. ¿Instalarla igualmente? "
                              "Solo funciona en apps de depuración o con el móvil en modo desarrollador.",
                              f"{Path(group[0]).name} is older than the installed one. Install it anyway? "
                              "This only works for debuggable apps or phones in developer mode."),
                           ok=tr("Instalar igualmente", "Install anyway")):
                    self.install_files(group, split, downgrade=True)
                return
            if error.code == "INSTALL_FAILED_UPDATE_INCOMPATIBLE" and error.package:
                if confirm(self, tr("La firma no coincide", "Signature mismatch"),
                           tr(f"La versión instalada de {error.package} está firmada de otra forma. Para instalar "
                              "esta hay que desinstalar la actual y se perderán sus datos. ¿Continuar?",
                              f"The installed version of {error.package} is signed differently. To install this "
                              "one the current one must be uninstalled and its data will be lost. Continue?"),
                           ok=tr("Desinstalar e instalar", "Uninstall and install"), danger=True):
                    self._reinstall(error.package, group, split)
                return
        lines = "\n".join(f"• {Path(g[0]).name}: {e}" for g, e in failures)
        confirm(self, tr("No se pudo instalar", "Could not install"), lines, ok=tr("Entendido", "Got it"))

    def _reinstall(self, package, group, split):
        serial = self.serial

        def work():
            android.uninstall(serial, package)
            android.install_apks(serial, group, split=split)

        self.run_task(work, done=self._after, fail=self._after, ok_title=tr("Instalación completada",
                                                                           "Installation complete"),
                      ok_text=package, err_title=tr("No se pudo instalar", "Could not install"))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = expand_apk_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        if paths:
            event.acceptProposedAction()
            self.install_files(paths)

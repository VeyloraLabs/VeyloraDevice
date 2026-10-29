from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon as FIF, FluentWindow, NavigationItemPosition

from .. import __version__, assets, i18n, update
from ..core import tools
from ..i18n import tr
from .components import toast
from .android_apps_tab import AndroidAppsTab
from .android_base import AndroidMonitor
from .android_files_tab import AndroidFilesTab
from .android_tab import AndroidTab
from .android_tools_tab import AndroidToolsTab
from .condition_tab import ConditionTab
from .device_tab import DeviceTab
from .extras_tab import ExtrasTab
from .firmware_tab import FirmwareTab
from .flash_tab import FlashTab
from .monitor import DeviceMonitor
from .icons import android_icon, apple_icon
from .settings_tab import SettingsTab
from .update_dialog import UpdateDialog


class MainWindow(FluentWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"VeyloraDevice · {__version__}")
        self.setWindowIcon(assets.app_icon())
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1180, screen.width() - 60), min(800, screen.height() - 60))
        self.setMinimumSize(900, 600)
        self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)
        self.navigationInterface.setExpandWidth(250)
        self.navigationInterface.setCollapsible(False)

        self.monitor = DeviceMonitor(self)
        self.android_monitor = AndroidMonitor(self)
        self.t_dev = DeviceTab(self.monitor)
        self.t_android = AndroidTab(self.android_monitor)
        self.t_android_apps = AndroidAppsTab(self.android_monitor)
        self.t_android_files = AndroidFilesTab(self.android_monitor)
        self.t_android_tools = AndroidToolsTab(self.android_monitor)
        self.t_fw = FirmwareTab(self.monitor)
        self.t_flash = FlashTab(self.monitor)
        self.t_extra = ExtrasTab(self.monitor)
        self.t_value = ConditionTab(self.monitor)
        self.t_settings = SettingsTab()

        self._nav = []
        self._group_apple = self.navigationInterface.addItem(
            "group-apple", apple_icon(), tr("Apple", "Apple"), selectable=False,
            position=NavigationItemPosition.TOP)
        self._nav.append((self._group_apple, "Apple", "Apple"))

        for page, icon, es, en in (
                (self.t_dev, FIF.PHONE, "Dispositivo", "Device"),
                (self.t_fw, FIF.DOWNLOAD, "Firmware", "Firmware"),
                (self.t_flash, FIF.SYNC, "Flasheo", "Flash"),
                (self.t_extra, FIF.DEVELOPER_TOOLS, "Herramientas", "Tools"),
                (self.t_value, FIF.TAG, "Estado y valor", "Condition & value")):
            self._add_group_page(page, icon, es, en, "group-apple")

        self.navigationInterface.addSeparator(NavigationItemPosition.TOP)
        self._group_android = self.navigationInterface.addItem(
            "group-android", android_icon(), tr("Android", "Android"), selectable=False,
            position=NavigationItemPosition.TOP)
        self._nav.append((self._group_android, "Android", "Android"))
        for page, icon, es, en in (
                (self.t_android, FIF.PHONE, "Dispositivo", "Device"),
                (self.t_android_apps, FIF.APPLICATION, "Aplicaciones", "Apps"),
                (self.t_android_files, FIF.FOLDER, "Archivos", "Files"),
                (self.t_android_tools, FIF.DEVELOPER_TOOLS, "Herramientas", "Tools")):
            self._add_group_page(page, icon, es, en, "group-android")
        self._group_apple.setExpanded(True)
        self._group_android.setExpanded(True)

        self.navigationInterface.addSeparator(NavigationItemPosition.BOTTOM)
        settings_item = self.addSubInterface(self.t_settings, FIF.SETTING, tr("Ajustes", "Settings"),
                                             NavigationItemPosition.BOTTOM)
        self._nav.append((settings_item, "Ajustes", "Settings"))
        i18n.on_change(self._retranslate)

        missing = tools.missing_tools()
        if missing:
            toast(self, "warn", tr("Faltan herramientas", "Missing tools"),
                  ", ".join(missing) + "\n" + tools.INSTALL_HINT, 12000)

        self.t_android.goto_apps.connect(lambda: self.switchTo(self.t_android_apps))
        self.t_android_tools.goto_device.connect(lambda: self.switchTo(self.t_android))
        self.t_android_tools.goto_apps.connect(lambda: self.switchTo(self.t_android_apps))
        self.t_android_tools.goto_files.connect(lambda: self.switchTo(self.t_android_files))
        self.t_android_tools.open_report.connect(self._goto_android_report)
        self.t_dev.goto_firmwares.connect(self._goto_fw)
        self.t_dev.open_report.connect(self._goto_report)
        self.t_fw.ipsw_ready.connect(self._ipsw_ready)
        self.monitor.start()
        self.android_monitor.start()

        self.updater = update.UpdateChecker(self)
        self.updater.found.connect(self._show_update)
        self.updater.finished.connect(self._update_finished)
        self.t_settings.check_updates.connect(lambda: self.updater.check(True))
        self.updater.start()

    def _add_group_page(self, page, icon, es, en, parent_route):
        item = self.addSubInterface(page, icon, tr(es, en), NavigationItemPosition.TOP,
                                    parent=parent_route)
        self._nav.append((item, es, en))
        return item

    def _retranslate(self, _code):
        for item, es, en in self._nav:
            item.setText(tr(es, en))

    def _show_update(self, release):
        UpdateDialog(release, self).exec()

    def _update_finished(self, release, error, manual):
        if not manual:
            return
        if error:
            toast(self, "err", tr("No se pudo comprobar", "Could not check"), error, 6000)
        elif not release or not update.is_newer(release["version"], __version__):
            toast(self, "ok", tr("Estás al día", "You are up to date"), tr(f"Versión {__version__}", f"Version {__version__}"), 4000)

    def _goto_fw(self, ident):
        self.switchTo(self.t_fw)
        self.t_fw.set_identifier(ident)

    def _goto_report(self):
        self.switchTo(self.t_extra)
        self.t_extra.open_report()

    def _goto_android_report(self):
        self.switchTo(self.t_android)
        self.t_android._report_pdf()

    def _ipsw_ready(self, path):
        self.t_flash.set_ipsw(path)
        toast(self, "ok", tr("IPSW enviado a Flasheo", "IPSW sent to Flash"), path.rsplit("/", 1)[-1], 4000)

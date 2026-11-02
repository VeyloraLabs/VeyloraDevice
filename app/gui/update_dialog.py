from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from qfluentwidgets import BodyLabel, CaptionLabel, IndeterminateProgressBar, MessageBoxBase, PushButton, SubtitleLabel

from .. import __version__, theme, update
from ..dispatch import run_async
from ..i18n import tr


class UpdateDialog(MessageBoxBase):
    download_progress = Signal(int, int)

    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.release = release
        self._downloading = False
        self._downloaded_path = None
        self.viewLayout.addWidget(SubtitleLabel(tr("Hay una versión nueva", "A new version is available")))
        line = BodyLabel(tr(f"VeyloraDevice {release['version']} ya está disponible. Tienes la {__version__}.",
                            f"VeyloraDevice {release['version']} is available. You have {__version__}."))
        line.setWordWrap(True)
        self.viewLayout.addWidget(line)
        notes = release["notes"][:1800] + ("…" if len(release["notes"]) > 1800 else "")
        if notes:
            caption = CaptionLabel(tr("Novedades", "What's new"))
            caption.setStyleSheet(f"color:{theme.MUTED}")
            self.viewLayout.addWidget(caption)
            box = QPlainTextEdit()
            box.setReadOnly(True)
            box.setPlainText(notes)
            box.setMinimumHeight(150)
            box.setMaximumHeight(220)
            self.viewLayout.addWidget(box)
        asset = release.get("asset")
        if asset:
            file_label = CaptionLabel(tr(f"Se descargará: {asset[0]}", f"Will download: {asset[0]}"))
            file_label.setStyleSheet(f"color:{theme.MUTED}")
            self.viewLayout.addWidget(file_label)
        self.progress = IndeterminateProgressBar()
        self.progress.hide()
        self.viewLayout.addWidget(self.progress)
        self.status = CaptionLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{theme.MUTED}")
        self.status.hide()
        self.viewLayout.addWidget(self.status)
        self.download_progress.connect(self._progress)
        self.skip_button = PushButton(tr("No avisar de esta versión", "Don't remind me about this version"))
        self.skip_button.clicked.connect(self._skip)
        self.viewLayout.addWidget(self.skip_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.yesButton.setText(tr("Descargar", "Download"))
        self.cancelButton.setText(tr("Más tarde", "Later"))
        self.widget.setMinimumWidth(520)

    def _skip(self):
        if self._downloading:
            return
        update.skip_version(self.release["version"])
        self.reject()

    def validate(self):
        if self._downloading:
            return False
        if self._downloaded_path:
            return self._launch_download()
        if not self.release.get("asset"):
            QDesktopServices.openUrl(QUrl(self.release["url"]))
            return True
        self._downloading = True
        self.yesButton.setEnabled(False)
        self.cancelButton.setEnabled(False)
        self.skip_button.setEnabled(False)
        self.yesButton.setText(tr("Descargando…", "Downloading…"))
        self.status.setText(tr("Descargando y verificando el instalador…",
                               "Downloading and verifying the installer…"))
        self.status.show()
        self.progress.show()
        run_async(lambda: update.download_asset(
            self.release, lambda done, total: self.download_progress.emit(done, total)),
            self._downloaded, self._download_failed)
        return False

    def _progress(self, done, total):
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, done * 100 // total))
            self.status.setText(tr(f"Descargando… {done // 1024} / {total // 1024} KB",
                                   f"Downloading… {done // 1024} / {total // 1024} KB"))
        else:
            self.progress.setRange(0, 0)

    def _downloaded(self, path):
        self._downloading = False
        self._downloaded_path = path
        self.progress.hide()
        self.yesButton.setEnabled(True)
        self.yesButton.setText(tr("Instalar ahora", "Install now"))
        self.cancelButton.setEnabled(True)
        self.cancelButton.setText(tr("Cerrar", "Close"))
        self.skip_button.setEnabled(True)
        self.status.setText(tr("Descarga verificada. Preparando el instalador…",
                               "Download verified. Preparing the installer…"))
        QTimer.singleShot(0, self._launch_download)

    def _download_failed(self, error):
        self._downloading = False
        self.progress.hide()
        self.yesButton.setEnabled(True)
        self.yesButton.setText(tr("Reintentar descarga", "Retry download"))
        self.cancelButton.setEnabled(True)
        self.skip_button.setEnabled(True)
        self.status.setText(tr(f"No se pudo descargar la actualización: {error}",
                               f"Could not download the update: {error}"))
        self.status.show()

    def _launch_download(self):
        if not self._downloaded_path:
            return False
        try:
            result = update.launch_installer(self._downloaded_path)
        except (OSError, RuntimeError) as error:
            self.status.setText(tr(f"No se pudo iniciar el instalador: {error}",
                                   f"Could not launch the installer: {error}"))
            self.status.show()
            return False
        if result == "installer":
            self.status.setText(tr("El instalador está abierto. VeyloraDevice se cerrará para completar la actualización.",
                                   "The installer is open. VeyloraDevice will close to complete the update."))
            QTimer.singleShot(700, QApplication.quit)
            return True
        self.status.setText(tr("Se abrió el archivo descargado. Sigue las instrucciones del instalador del sistema.",
                               "The downloaded file was opened. Follow the system installer instructions."))
        self.status.show()
        self.yesButton.setEnabled(False)
        self.yesButton.setText(tr("Archivo abierto", "File opened"))
        self.cancelButton.setText(tr("Cerrar", "Close"))
        return False

    def reject(self):
        if self._downloading:
            return
        super().reject()

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QPlainTextEdit
from qfluentwidgets import BodyLabel, CaptionLabel, MessageBoxBase, PushButton, SubtitleLabel

from .. import __version__, theme, update
from ..i18n import tr


class UpdateDialog(MessageBoxBase):
    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.release = release
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
        self.skip_button = PushButton(tr("No avisar de esta versión", "Don't remind me about this version"))
        self.skip_button.clicked.connect(self._skip)
        self.viewLayout.addWidget(self.skip_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.yesButton.setText(tr("Descargar", "Download"))
        self.cancelButton.setText(tr("Más tarde", "Later"))
        self.widget.setMinimumWidth(520)

    def _skip(self):
        update.skip_version(self.release["version"])
        self.reject()

    def validate(self):
        asset = self.release.get("asset")
        QDesktopServices.openUrl(QUrl(asset[1] if asset else self.release["url"]))
        return True

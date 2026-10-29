from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout
from qfluentwidgets import BodyLabel, CaptionLabel, ComboBox, FluentIcon as FIF, PushButton, SubtitleLabel, SwitchButton

from .. import __version__, assets, i18n, privacy, theme, update
from ..i18n import tr
from .components import Page, card_frame, section


class SettingsTab(Page):

    check_updates = Signal()

    def _set_switch_texts(self):
        for switch in (getattr(self, "hide_switch", None), getattr(self, "auto_switch", None)):
            if switch is not None:
                switch.setOnText(tr("Sí", "On"))
                switch.setOffText(tr("No", "Off"))

    def __init__(self, parent=None):
        super().__init__("settings", ("Ajustes", "Settings"), ("Idioma y créditos.", "Language and credits."), parent=parent)

        self.body.addWidget(section("Idioma", "Language"))
        card, cl = card_frame(QHBoxLayout)
        cl.addWidget(i18n.bind(BodyLabel(), "setText", "Idioma de la interfaz", "Interface language"), 1)
        self.language = ComboBox()
        self.language.addItem("English", userData="en")
        self.language.addItem("Español", userData="es")
        self.language.setCurrentIndex(max(0, self.language.findData(i18n.lang())))
        self.language.setMinimumWidth(160)
        self.language.currentIndexChanged.connect(lambda _i: i18n.set_lang(self.language.currentData()))
        cl.addWidget(self.language)
        self.body.addWidget(card)

        self.body.addWidget(section("Privacidad", "Privacy"))
        privacy_card, pl = card_frame(QHBoxLayout)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(i18n.bind(BodyLabel(), "setText", "Ocultar contenido sensible", "Hide sensitive content"))
        note = CaptionLabel("")
        i18n.bind(note, "setText",
                  "Oculta números de serie, IMEI, UDID, ECID, MAC, IP, teléfono y el nombre del dispositivo. Para ver un dato, "
                  "haz 5 clics sobre la parte oculta: se muestra 5 segundos y vuelve a ocultarse. Los informes también salen sin esos datos.",
                  "Hides serial numbers, IMEI, UDID, ECID, MAC, IP, phone number and the device name. To see a value, click "
                  "5 times on the hidden part: it shows for 5 seconds and hides again. Reports also leave those values out.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.MUTED}")
        texts.addWidget(note)
        pl.addLayout(texts, 1)
        self.hide_switch = SwitchButton()
        self.hide_switch.setChecked(privacy.enabled())
        self._set_switch_texts()
        i18n.on_change(lambda _c: self._set_switch_texts())
        self.hide_switch.checkedChanged.connect(privacy.set_enabled)
        pl.addWidget(self.hide_switch)
        self.body.addWidget(privacy_card)

        self.body.addWidget(section("Actualizaciones", "Updates"))
        update_card, ul = card_frame(QHBoxLayout)
        utexts = QVBoxLayout()
        utexts.setSpacing(2)
        utexts.addWidget(i18n.bind(BodyLabel(), "setText", "Avisarme de nuevas versiones", "Notify me about new versions"))
        unote = CaptionLabel("")
        i18n.bind(unote, "setText", f"Versión instalada: {__version__}. Se consulta GitHub al abrir y cada pocas horas.",
                  f"Installed version: {__version__}. GitHub is checked on start and every few hours.")
        unote.setStyleSheet(f"color:{theme.MUTED}")
        utexts.addWidget(unote)
        ul.addLayout(utexts, 1)
        check = PushButton(FIF.SYNC, "")
        i18n.bind(check, "setText", "Buscar ahora", "Check now")
        check.clicked.connect(self.check_updates.emit)
        ul.addWidget(check)
        self.auto_switch = SwitchButton()
        self.auto_switch.setChecked(update.auto_enabled())
        self.auto_switch.checkedChanged.connect(update.set_auto)
        self._set_switch_texts()
        ul.addWidget(self.auto_switch)
        self.body.addWidget(update_card)

        self.body.addWidget(section("Acerca de", "About"))
        about, al = card_frame(QHBoxLayout, margins=(22, 18, 22, 18), spacing=22)
        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if assets.exists("banner.png"):
            logo.setPixmap(assets.banner_pixmap(190))
        al.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        info = QVBoxLayout()
        info.setSpacing(6)
        info.addWidget(SubtitleLabel(f"VeyloraDevice  ·  v{__version__}"))
        info.addWidget(i18n.bind(BodyLabel(), "setText", "Gestión de dispositivos Apple y Android",
                                 "Apple and Android device management"))
        by = CaptionLabel("")
        i18n.bind(by, "setText", "Un producto de VeyloraLabs · creado por hugovadero", "A VeyloraLabs product · created by hugovadero")
        by.setStyleSheet(f"color:{theme.MUTED}")
        info.addWidget(by)
        made = CaptionLabel("")
        i18n.bind(made, "setText", "Hecho con ♥ en Andalucía, España", "Made with ♥ in Andalusia, Spain")
        made.setStyleSheet(f"color:{theme.ACCENT}")
        info.addWidget(made)
        row = QHBoxLayout()
        gh = PushButton(FIF.GITHUB, "GitHub · hugovadero")
        yt = PushButton(FIF.VIDEO if hasattr(FIF, "VIDEO") else FIF.PLAY, "YouTube · hugovadero")
        gh.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/hugovadero")))
        yt.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.youtube.com/@hugovadero")))
        row.addWidget(gh)
        row.addWidget(yt)
        row.addStretch(1)
        info.addSpacing(6)
        info.addLayout(row)
        al.addLayout(info, 1)
        self.body.addWidget(about)
        self.body.addStretch(1)

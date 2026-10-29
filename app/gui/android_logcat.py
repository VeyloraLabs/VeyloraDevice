from collections import deque
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtGui import QColor, QFontDatabase, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QPlainTextEdit, QVBoxLayout
from qfluentwidgets import CaptionLabel, ComboBox, FluentIcon as FIF, PushButton, SearchLineEdit

from .. import privacy, theme
from ..core import android
from ..dispatch import run_async
from ..i18n import tr
from .components import toast

MAX_LINES = 30000
MAX_VISIBLE = 5000
COLORS = {"E": "#ff6b6b", "F": "#ff6b6b", "A": "#ff6b6b", "W": "#f5a524", "D": "#8b919b", "V": "#6f757f"}


class LogcatWindow(QDialog):
    def __init__(self, serial, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.setWindowTitle("Logcat" if privacy.enabled() else f"Logcat · {serial}")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(1000, 640)
        self._lines = deque(maxlen=MAX_LINES)
        self._pending = []
        self._tail = ""
        self._paused = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.level = ComboBox()
        for text, value in ((tr("Todo", "Everything"), "V"), ("Debug", "D"), ("Info", "I"),
                            (tr("Avisos", "Warnings"), "W"), (tr("Errores", "Errors"), "E")):
            self.level.addItem(text, userData=value)
        self.level.currentIndexChanged.connect(lambda _i: self._rerender())
        self.search = SearchLineEdit()
        self.search.setPlaceholderText(tr("Filtrar por texto, etiqueta o paquete…", "Filter by text, tag or package…"))
        self.search.textChanged.connect(lambda _t: self._rerender())
        self.pause_button = PushButton(FIF.PAUSE, tr("Pausar", "Pause"))
        self.pause_button.clicked.connect(self._toggle_pause)
        self.clear_button = PushButton(FIF.BROOM, tr("Limpiar", "Clear"))
        self.clear_button.clicked.connect(self._clear)
        self.save_button = PushButton(FIF.SAVE, tr("Guardar…", "Save…"))
        self.save_button.clicked.connect(self._save)
        top.addWidget(CaptionLabel(tr("Nivel", "Level")))
        top.addWidget(self.level)
        top.addWidget(self.search, 1)
        for button in (self.pause_button, self.clear_button, self.save_button):
            top.addWidget(button)
        lay.addLayout(top)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setMaximumBlockCount(MAX_VISIBLE)
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.view.setStyleSheet("QPlainTextEdit { background:#0e0f12; color:#cfd3da; border:1px solid #2b2f35; "
                                "border-radius:10px; padding:8px; }")
        lay.addWidget(self.view, 1)
        self.status = CaptionLabel("")
        self.status.setStyleSheet(f"color:{theme.MUTED}")
        lay.addWidget(self.status)

        self._formats = {}
        for level, color in COLORS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            self._formats[level] = fmt
        self._plain = QTextCharFormat()

        self.proc = QProcess(self)
        self.proc.setProgram("adb")
        self.proc.setArguments(["-s", serial, "logcat", "-v", "threadtime"])
        self.proc.readyReadStandardOutput.connect(self._on_data)
        self.proc.finished.connect(self._on_finished)
        self.proc.errorOccurred.connect(self._on_error)
        self._flush = QTimer(self)
        self._flush.setInterval(150)
        self._flush.timeout.connect(self._flush_pending)
        self._flush.start()
        self.proc.start()
        self._update_status()

    def _on_data(self):
        text = self._tail + bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        *lines, self._tail = text.split("\n")
        for line in lines:
            line = line.rstrip("\r")
            if not line:
                continue
            self._lines.append(line)
            if not self._paused and self._passes(line):
                self._pending.append(line)

    def _on_finished(self, code, _status):
        self._flush_pending()
        self.status.setText(tr(f"Logcat terminado (código {code}). ¿Sigue conectado el móvil?",
                               f"Logcat ended (code {code}). Is the phone still connected?"))

    def _on_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.status.setText(tr("No se pudo iniciar adb.", "Could not start adb."))

    def _passes(self, line):
        if not android.level_allowed(android.parse_logcat_level(line), self.level.currentData() or "V"):
            return False
        query = self.search.text().strip().lower()
        return not query or query in line.lower()

    def _append(self, lines):
        scroll = self.view.verticalScrollBar()
        at_bottom = scroll.value() >= scroll.maximum() - 4
        cursor = QTextCursor(self.view.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for line in lines:
            cursor.insertText(line + "\n", self._formats.get(android.parse_logcat_level(line), self._plain))
        if at_bottom:
            scroll.setValue(scroll.maximum())

    def _flush_pending(self):
        if self._pending and not self._paused:
            lines, self._pending = self._pending, []
            self._append(lines)
            self._update_status()

    def _rerender(self):
        self._pending = []
        self.view.clear()
        shown = [line for line in self._lines if self._passes(line)][-MAX_VISIBLE:]
        self._append(shown)
        self._update_status()

    def _update_status(self):
        state = tr("en pausa", "paused") if self._paused else tr("en vivo", "live")
        self.status.setText(tr(f"{len(self._lines)} líneas recibidas · {state}",
                               f"{len(self._lines)} lines received · {state}"))

    def _toggle_pause(self):
        self._paused = not self._paused
        self.pause_button.setText(tr("Seguir", "Resume") if self._paused else tr("Pausar", "Pause"))
        self.pause_button.setIcon(FIF.PLAY if self._paused else FIF.PAUSE)
        if not self._paused:
            self._rerender()
        self._update_status()

    def _clear(self):
        self._lines.clear()
        self._pending = []
        self.view.clear()
        run_async(lambda: android._run_adb(["-s", self.serial, "logcat", "-c"], timeout=15), None, lambda _e: None)
        self._update_status()

    def _save(self):
        lines = [line for line in self._lines if self._passes(line)]
        if not lines:
            toast(self, "warn", tr("Nada que guardar", "Nothing to save"),
                  tr("Todavía no hay líneas con ese filtro.", "There are no lines with that filter yet."))
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("Guardar logcat", "Save logcat"),
                                              str(Path.home() / f"logcat-{self.serial}.txt".replace(":", "_")),
                                              "Text (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            toast(self, "err", tr("No se pudo guardar", "Could not save"), str(exc), 6000)
            return
        toast(self, "ok", tr("Guardado", "Saved"), path, 3500)

    def closeEvent(self, event):
        self._flush.stop()
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            self.proc.terminate()
            if not self.proc.waitForFinished(1500):
                self.proc.kill()
        super().closeEvent(event)

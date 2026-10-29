import re

from PySide6.QtCore import QProcess, QTimer, Signal
from PySide6.QtGui import QFontDatabase, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget
from qfluentwidgets import ProgressBar

from ..i18n import tr

PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


class LogPanel(QWidget):

    finished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.log.setStyleSheet("QPlainTextEdit { background:#0e0f12; color:#cfd3da; border:1px solid #2b2f35; "
                               "border-radius:10px; padding:8px; }")
        self.bar = ProgressBar()
        self.bar.setRange(0, 100)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.log, 1)
        lay.addWidget(self.bar)
        self.proc = None
        self._cr = False

    def running(self):
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    def clear(self):
        self.log.clear()
        self.bar.setValue(0)

    def println(self, text):
        self._feed(text + "\n")

    def run(self, program, args):
        if self.running():
            return False
        self.bar.setValue(0)
        self.println("$ " + " ".join([program] + list(args)))
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        p.readyRead.connect(self._on_ready)
        p.finished.connect(self._on_finished)
        p.errorOccurred.connect(self._on_error)
        self.proc = p
        p.start(program, list(args))
        return True

    def stop(self):
        if self.running():
            p = self.proc
            p.terminate()
            QTimer.singleShot(4000, lambda: p.kill() if p.state() != QProcess.ProcessState.NotRunning else None)

    def _on_ready(self):
        text = bytes(self.proc.readAll()).decode("utf-8", "replace")
        found = PCT.findall(text)
        if found:
            v = float(found[-1])
            if 0 <= v <= 100:
                self.bar.setValue(int(v))
        self._feed(text)

    def _on_finished(self, code, _status):
        self.println(tr(f"\n[terminado con código {code}]", f"\n[finished with code {code}]"))
        if code == 0:
            self.bar.setValue(100)
        self.finished.emit(code)

    def _on_error(self, err):
        if err == QProcess.ProcessError.FailedToStart:
            self.println(tr("ERROR: no se pudo ejecutar el comando (¿está instalado? mira el README)", "ERROR: could not run the command (is it installed? see the README)"))
            self.finished.emit(-1)

    def _feed(self, text):
        for tok in re.split(r"(\r|\n)", text):
            if not tok:
                continue
            c = self.log.textCursor()
            c.movePosition(QTextCursor.MoveOperation.End)
            if tok == "\r":
                self._cr = True
            elif tok == "\n":
                c.insertBlock()
                self._cr = False
            else:
                if self._cr:
                    c.movePosition(QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor)
                    c.removeSelectedText()
                    self._cr = False
                c.insertText(tok)
        self.log.moveCursor(QTextCursor.MoveOperation.End)

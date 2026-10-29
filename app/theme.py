from PySide6.QtGui import QColor
from qfluentwidgets import Theme, setTheme, setThemeColor

ACCENT = "#00f49f"
BG = "#121214"
CARD = "#1b1d21"
BORDER = "#2b2f35"
MUTED = "#8b919b"
DANGER = "#e5484d"
WARN = "#f5a524"
OK = ACCENT


def apply(app):
    setTheme(Theme.DARK)
    setThemeColor(QColor(ACCENT), save=False)
    app.setStyleSheet(f"""
        QDialog {{ background: {BG}; }}
        QDialog QLabel {{ color: #e6e8ec; }}
        QDialog QPushButton {{ padding: 7px 16px; border: 1px solid {BORDER}; border-radius: 8px;
                              background: #24272d; color: #e6e8ec; }}
        QDialog QPushButton:hover {{ border-color: {ACCENT}; background: #2a2f36; }}
        QDialog QPushButton:pressed {{ background: #1f2328; }}
        QDialog QPushButton:disabled {{ color: #666; background: #1c1e22; }}
        QDialog QLineEdit, QDialog QComboBox {{ background: #1b1d21; border: 1px solid {BORDER};
                              border-radius: 8px; padding: 6px 10px; color: #e6e8ec; }}
        QDialog QLineEdit:focus, QDialog QComboBox:focus {{ border-color: {ACCENT}; }}
        QDialog QTreeWidget, QDialog QTableView, QDialog QTableWidget, QDialog QPlainTextEdit {{
            background: #17181b; border: 1px solid {BORDER}; border-radius: 10px;
            alternate-background-color: #1b1d21; gridline-color: {BORDER}; color: #e6e8ec; }}
        QDialog QHeaderView::section {{ background: #1f2227; color: {MUTED}; border: none; padding: 6px 8px; }}
        QDialog QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid #555; background: #1b1d21; }}
        QDialog QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
        QDialog QScrollBar:vertical {{ background: transparent; width: 10px; }}
        QDialog QScrollBar::handle:vertical {{ background: #3a3f47; border-radius: 5px; min-height: 30px; }}
        QDialog QScrollBar::add-line, QDialog QScrollBar::sub-line {{ height: 0; }}
        QToolTip {{ background: #24272d; color: #e6e8ec; border: 1px solid {BORDER}; padding: 4px 8px; }}
    """)

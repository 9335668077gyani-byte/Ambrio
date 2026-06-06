# app.py
"""
Ambrio Desktop — PyQt6 UI entry point.
Launch router_service.py first, then run this.
Or use ambrio.ps1 to start both automatically.
"""
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui     import QFont, QIcon
from ambrio.ui.main_window import MainWindow

QSS_PATH = Path(__file__).parent / "ambrio" / "ui" / "theme" / "neumorphic.qss"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Ambrio")
    app.setOrganizationName("Ambrio AI")
    app.setApplicationVersion("3.0.0")

    # Load Neumorphic stylesheet
    if QSS_PATH.exists():
        app.setStyleSheet(QSS_PATH.read_text(encoding="utf-8"))

    # System font fallback
    app.setFont(QFont("Segoe UI", 12))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

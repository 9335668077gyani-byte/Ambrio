# ambrio/ui/input_bar.py
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QTextEdit, QPushButton
from PyQt6.QtCore    import Qt, pyqtSignal
from PyQt6.QtGui     import QKeyEvent


class _EnterTextEdit(QTextEdit):
    """QTextEdit that emits `submitted` on Enter (without Shift)."""
    submitted = pyqtSignal()

    def keyPressEvent(self, e: QKeyEvent):
        no_shift = not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and no_shift:
            self.submitted.emit()
        else:
            super().keyPressEvent(e)


class InputBar(QWidget):
    submitted = pyqtSignal(str)   # emits trimmed text on Enter / Send button

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(10)

        self._input = _EnterTextEdit()
        self._input.setObjectName("chatInput")
        self._input.setPlaceholderText("Message Ambrio…  (Shift+Enter for newline)")
        self._input.setMaximumHeight(120)
        self._input.setMinimumHeight(50)
        self._input.submitted.connect(self._on_submit)

        self._btn = QPushButton("Send ↑")
        self._btn.setObjectName("sendBtn")
        self._btn.setFixedWidth(90)
        self._btn.setFixedHeight(50)
        self._btn.clicked.connect(self._on_submit)

        layout.addWidget(self._input)
        layout.addWidget(self._btn)

    def _on_submit(self):
        text = self._input.toPlainText().strip()
        if text:
            self._input.clear()
            self.submitted.emit(text)

    def set_enabled(self, enabled: bool):
        self._input.setEnabled(enabled)
        self._btn.setEnabled(enabled)
        if enabled:
            self._input.setFocus()

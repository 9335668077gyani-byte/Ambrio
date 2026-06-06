# ambrio/ui/chat_widget.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class MessageBubble(QFrame):
    def __init__(self, text: str, role: str):
        super().__init__()
        self.setObjectName("userBubble" if role == "user" else "assistantBubble")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        # Role label
        role_label = QLabel("You" if role == "user" else "⚡ Ambrio")
        role_label.setStyleSheet(
            f"color: {'#7c6af7' if role == 'user' else '#5de0e6'};"
            "font-size: 11px; font-weight: 700; letter-spacing: 0.5px;"
        )
        layout.addWidget(role_label)

        # Content label
        self._content = QLabel(text)
        self._content.setWordWrap(True)
        self._content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._content.setFont(QFont("Segoe UI", 13))
        self._content.setStyleSheet("color: #d4d8f0; line-height: 1.5;")
        layout.addWidget(self._content)

    def append_token(self, token: str):
        self._content.setText(self._content.text() + token)

    def set_text(self, text: str):
        self._content.setText(text)


class ChatWidget(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Auto-scroll to bottom on content change
        self._scroll.verticalScrollBar().rangeChanged.connect(
            lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            )
        )

        self._container = QWidget()
        self._layout    = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setSpacing(6)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

        self._active_bubble: MessageBubble | None = None

    def add_user_message(self, text: str) -> None:
        bubble = MessageBubble(text, "user")
        self._layout.addWidget(bubble)

    def begin_assistant_message(self) -> None:
        bubble = MessageBubble("", "assistant")
        self._layout.addWidget(bubble)
        self._active_bubble = bubble

    def append_token(self, token: str) -> None:
        if self._active_bubble:
            self._active_bubble.append_token(token)

    def finalize_assistant_message(self) -> None:
        self._active_bubble = None

    def add_system_notice(self, text: str) -> None:
        """Add a dim system notice (errors, tool results, etc.)."""
        label = QLabel(f"ℹ {text}")
        label.setStyleSheet(
            "color: #5a6080; font-size: 11px; padding: 4px 12px; font-style: italic;"
        )
        self._layout.addWidget(label)

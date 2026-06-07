# ambrio/ui/sidebar.py
import uuid
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel
)
from PyQt6.QtCore import pyqtSignal, Qt


class Sidebar(QWidget):
    session_selected = pyqtSignal(str)   # emits full session_id on selection
    new_session      = pyqtSignal(str)   # emits new session_id on creation
    settings_clicked = pyqtSignal()      # emits when Settings button pressed

    def __init__(self):
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(230)
        self._id_map: dict[str, str] = {}  # display label → session_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(10)

        title = QLabel("⚡ Ambrio")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        tagline = QLabel("Local · Private · Autonomous")
        tagline.setStyleSheet("color: #5a6080; font-size: 11px; font-weight: 500;")
        layout.addWidget(tagline)

        self._new_btn = QPushButton("+ New Session")
        self._new_btn.setObjectName("newSessionBtn")
        self._new_btn.clicked.connect(self._create_session)
        layout.addWidget(self._new_btn)

        sessions_label = QLabel("SESSIONS")
        sessions_label.setStyleSheet(
            "color: #3a4060; font-size: 10px; font-weight: 700; letter-spacing: 1.5px; padding-top: 8px;"
        )
        layout.addWidget(sessions_label)

        self._list = QListWidget()
        self._list.setObjectName("sessionList")
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)
        layout.addStretch()

        # Settings button at bottom
        self._settings_btn = QPushButton("⚙  API Settings")
        self._settings_btn.setObjectName("settingsBtn")
        self._settings_btn.clicked.connect(self.settings_clicked)
        self._settings_btn.setStyleSheet(
            "QPushButton#settingsBtn {"
            "  background: transparent;"
            "  border: 1px solid #3D3836;"
            "  border-radius: 6px;"
            "  color: #A8A29E;"
            "  font-size: 12px;"
            "  padding: 8px;"
            "  text-align: left;"
            "}"
            "QPushButton#settingsBtn:hover {"
            "  border-color: #CA8A04;"
            "  color: #CA8A04;"
            "  background: #CA8A0411;"
            "}"
        )
        layout.addWidget(self._settings_btn)

    def _create_session(self):
        sid   = str(uuid.uuid4())
        label = f"Session {sid[:8]}"
        self._add_item(sid, label)
        self.new_session.emit(sid)

    def _add_item(self, session_id: str, label: str):
        self._id_map[label] = session_id
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, session_id)
        self._list.addItem(item)
        self._list.setCurrentItem(item)

    def _on_item_clicked(self, item: QListWidgetItem):
        sid = item.data(Qt.ItemDataRole.UserRole)
        if sid:
            self.session_selected.emit(sid)

    def add_session(self, session_id: str, label: str | None = None) -> None:
        self._add_item(session_id, label or f"Session {session_id[:8]}")

# ambrio/ui/file_manager.py
"""
Ambrio File Manager Panel — browse, attach, and manage files from within the chat.
Slides in/out from the right side of the main window.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QFrame, QSizePolicy,
    QToolButton, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QIcon, QColor
from pathlib import Path

# ── File type icons (emoji fallback — no external assets needed) ──────────────
_EXT_ICONS = {
    '.pdf':  '📄', '.docx': '📝', '.doc': '📝', '.txt': '📃',
    '.xlsx': '📊', '.xls': '📊', '.csv': '📊',
    '.png':  '🖼', '.jpg': '🖼', '.jpeg': '🖼', '.gif': '🖼', '.bmp': '🖼',
    '.mp4':  '🎬', '.avi': '🎬', '.mov': '🎬',
    '.mp3':  '🎵', '.wav': '🎵',
    '.zip':  '🗜', '.rar': '🗜', '.7z': '🗜',
    '.py':   '🐍', '.js': '📜', '.html': '🌐', '.css': '🎨',
    '.exe':  '⚙️',  '.msi': '⚙️',
}
_DIR_ICON  = '📁'
_FILE_ICON = '📄'

# Quick-access folders
_QUICK_FOLDERS = [
    ('🖥  Desktop',    Path.home() / 'Desktop'),
    ('⬇  Downloads',  Path.home() / 'Downloads'),
    ('📂  Documents',  Path.home() / 'Documents'),
    ('🖼  Pictures',   Path.home() / 'Pictures'),
    ('🏠  Home',       Path.home()),
]


class FileManagerPanel(QWidget):
    """
    Collapsible file manager panel.
    Emits `file_attach_requested(path)` when user clicks Attach on a file.
    """
    file_attach_requested = pyqtSignal(str)   # absolute path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setObjectName("fileManagerPanel")
        self.setStyleSheet("""
            #fileManagerPanel {
                background: #0d0f1e;
                border-left: 1px solid #1e2236;
            }
            QLabel { color: #94a3b8; }
            QListWidget {
                background: #0d0f1e;
                border: none;
                color: #cbd5e1;
                font-size: 12px;
            }
            QListWidget::item { padding: 5px 8px; border-radius: 4px; }
            QListWidget::item:hover    { background: #1a1f35; }
            QListWidget::item:selected { background: #2d3561; color: #e2e8f0; }
            QLineEdit {
                background: #141828;
                border: 1px solid #2e3248;
                border-radius: 4px;
                color: #94a3b8;
                font-size: 11px;
                padding: 4px 8px;
            }
            QPushButton {
                background: #1e2236;
                border: 1px solid #2e3248;
                border-radius: 4px;
                color: #94a3b8;
                font-size: 11px;
                padding: 4px 10px;
            }
            QPushButton:hover { background: #2d3561; color: #e2e8f0; }
            QPushButton#attachBtn {
                background: #4f46e5;
                border: none;
                color: white;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton#attachBtn:hover { background: #6366f1; }
        """)

        self._current_path = Path.home() / 'Desktop'
        self._selected_file: Path | None = None
        self._build_ui()
        self._navigate(self._current_path)

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setStyleSheet("background: #111427; border-bottom: 1px solid #1e2236;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(12, 8, 8, 8)
        title = QLabel("📁  File Manager")
        title.setStyleSheet("color: #e2e8f0; font-weight: 700; font-size: 13px;")
        h_lay.addWidget(title)
        h_lay.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("background: transparent; border: none; color: #475569; font-size: 13px;")
        close_btn.clicked.connect(self.hide)
        h_lay.addWidget(close_btn)
        layout.addWidget(header)

        # Quick folders
        quick = QWidget()
        quick.setStyleSheet("background: #0f1120; border-bottom: 1px solid #1a1f35;")
        q_lay = QHBoxLayout(quick)
        q_lay.setContentsMargins(8, 6, 8, 6)
        q_lay.setSpacing(4)
        for label, folder in _QUICK_FOLDERS:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "background: #1a1f35; border: 1px solid #2e3248; border-radius: 3px; "
                "color: #94a3b8; font-size: 10px; padding: 3px 6px;"
            )
            btn.clicked.connect(lambda _, f=folder: self._navigate(f))
            q_lay.addWidget(btn)
        layout.addWidget(quick)

        # Path bar
        path_bar = QWidget()
        path_bar.setStyleSheet("background: #0f1120; padding: 2px;")
        pb_lay = QHBoxLayout(path_bar)
        pb_lay.setContentsMargins(8, 4, 8, 4)
        pb_lay.setSpacing(4)

        self._up_btn = QPushButton("↑")
        self._up_btn.setFixedSize(26, 26)
        self._up_btn.setToolTip("Go up one folder")
        self._up_btn.clicked.connect(self._go_up)
        pb_lay.addWidget(self._up_btn)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Path...")
        self._path_edit.returnPressed.connect(
            lambda: self._navigate(Path(self._path_edit.text()))
        )
        pb_lay.addWidget(self._path_edit)
        layout.addWidget(path_bar)

        # File list
        self._file_list = QListWidget()
        self._file_list.setFont(QFont("Segoe UI", 11))
        self._file_list.itemDoubleClicked.connect(self._on_double_click)
        self._file_list.itemClicked.connect(self._on_click)
        layout.addWidget(self._file_list, stretch=1)

        # Bottom action bar
        action_bar = QWidget()
        action_bar.setStyleSheet("background: #111427; border-top: 1px solid #1e2236;")
        a_lay = QVBoxLayout(action_bar)
        a_lay.setContentsMargins(8, 8, 8, 8)
        a_lay.setSpacing(6)

        self._selected_label = QLabel("No file selected")
        self._selected_label.setWordWrap(True)
        self._selected_label.setStyleSheet("color: #64748b; font-size: 10px;")
        a_lay.addWidget(self._selected_label)

        self._attach_btn = QPushButton("📎  Attach to Chat")
        self._attach_btn.setObjectName("attachBtn")
        self._attach_btn.setFixedHeight(34)
        self._attach_btn.setEnabled(False)
        self._attach_btn.clicked.connect(self._attach_selected)
        a_lay.addWidget(self._attach_btn)

        layout.addWidget(action_bar)

    # ── Navigation ────────────────────────────────────────────────────────────
    def _navigate(self, path: Path):
        try:
            path = path.expanduser().resolve()
            if not path.is_dir():
                path = path.parent
            self._current_path = path
            self._path_edit.setText(str(path))
            self._refresh_list()
            self._selected_file = None
            self._selected_label.setText("No file selected")
            self._attach_btn.setEnabled(False)
        except Exception as e:
            self._path_edit.setText(f"Error: {e}")

    def _go_up(self):
        self._navigate(self._current_path.parent)

    def _refresh_list(self):
        self._file_list.clear()
        try:
            entries = sorted(
                self._current_path.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower())
            )
            for entry in entries:
                if entry.name.startswith('.'):
                    continue
                icon = _DIR_ICON if entry.is_dir() else _EXT_ICONS.get(entry.suffix.lower(), _FILE_ICON)
                size_str = ''
                if entry.is_file():
                    sz = entry.stat().st_size
                    size_str = f'  {sz//1024} KB' if sz >= 1024 else f'  {sz} B'
                item = QListWidgetItem(f"{icon}  {entry.name}{size_str}")
                item.setData(Qt.ItemDataRole.UserRole, str(entry))
                if entry.is_dir():
                    item.setForeground(QColor('#7c6af7'))
                self._file_list.addItem(item)
        except PermissionError:
            item = QListWidgetItem("🔒  Permission denied")
            self._file_list.addItem(item)

    def _on_double_click(self, item: QListWidgetItem):
        path = Path(item.data(Qt.ItemDataRole.UserRole) or '')
        if path.is_dir():
            self._navigate(path)
        elif path.is_file():
            self._attach_selected()

    def _on_click(self, item: QListWidgetItem):
        path = Path(item.data(Qt.ItemDataRole.UserRole) or '')
        if path.is_file():
            self._selected_file = path
            self._selected_label.setText(f"📎 {path.name}")
            self._attach_btn.setEnabled(True)
        else:
            self._selected_file = None
            self._selected_label.setText("No file selected")
            self._attach_btn.setEnabled(False)

    def _attach_selected(self):
        if self._selected_file and self._selected_file.is_file():
            self.file_attach_requested.emit(str(self._selected_file))
            self._selected_label.setText(f"✅ Attached: {self._selected_file.name}")

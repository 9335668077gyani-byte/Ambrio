# ambrio/ui/file_manager.py
"""
Ambrio True File Manager Panel
================================
Full-featured embedded file manager using QFileSystemModel + QTreeView.

Features:
  ✅ Real filesystem browsing (QFileSystemModel)
  ✅ Drag & drop — move files between folders by dragging
  ✅ Copy / Cut / Paste  (Ctrl+C, Ctrl+X, Ctrl+V)
  ✅ Delete              (Delete key or context menu)
  ✅ Rename              (F2 key or context menu)
  ✅ New Folder          (Ctrl+Shift+N)
  ✅ Right-click context menu
  ✅ Quick access sidebar (Desktop, Downloads, Documents…)
  ✅ Address bar with manual path entry
  ✅ Status bar (selected count + sizes)
  ✅ Select All          (Ctrl+A)
  ✅ Column view: Name, Size, Type, Date
  ✅ Attach selected file to Ambrio chat
"""
import os, shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeView, QLineEdit, QFrame,
    QSizePolicy, QMenu, QInputDialog, QMessageBox,
    QAbstractItemView, QSplitter, QListWidget,
    QListWidgetItem, QApplication
)
from PyQt6.QtCore  import Qt, pyqtSignal, QDir, QModelIndex, QUrl, QMimeData, QSize
from PyQt6.QtGui   import QFont, QColor, QKeySequence, QShortcut, QAction, QIcon, QFileSystemModel


# ── Ambrio output folder (all converted/saved files go here) ─────────────────
OUTPUT_DIR = Path.home() / 'Documents' / 'Ambrio Output'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)   # create on import

# ── Quick access sidebar entries ──────────────────────────────────────────────
# Pinned entries (shown with accent colour at top)
_PINNED = [
    ('⚡  Ambrio Output', OUTPUT_DIR),
]

_QUICK = [
    ('🖥  Desktop',    Path.home() / 'Desktop'),
    ('⬇  Downloads',  Path.home() / 'Downloads'),
    ('📂  Documents',  Path.home() / 'Documents'),
    ('🖼  Pictures',   Path.home() / 'Pictures'),
    ('🎵  Music',      Path.home() / 'Music'),
    ('🏠  Home',       Path.home()),
    ('💾  C:\\',       Path('C:\\')),
]

_PANEL_STYLE = """
QWidget {
    background: #0d0f1e;
    color: #cbd5e1;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}

/* Tree view */
QTreeView {
    background: #0d0f1e;
    border: none;
    outline: none;
    alternate-background-color: #0f1120;
}
QTreeView::item {
    padding: 3px 4px;
    border-radius: 3px;
}
QTreeView::item:hover    { background: #1a1f35; }
QTreeView::item:selected { background: #2d3561; color: #e2e8f0; }
QTreeView QHeaderView::section {
    background: #111427;
    color: #64748b;
    border: none;
    border-bottom: 1px solid #1e2236;
    padding: 4px 8px;
    font-size: 11px;
}

/* Quick access list */
QListWidget {
    background: #080a14;
    border: none;
    border-right: 1px solid #1e2236;
    color: #94a3b8;
    font-size: 11px;
}
QListWidget::item { padding: 6px 10px; }
QListWidget::item:hover    { background: #141828; color: #e2e8f0; }
QListWidget::item:selected { background: #1e2540; color: #a5b4fc; }
QListWidget::item[pinned="true"] { color: #a5b4fc; font-weight: 700; background: #13142a; }

/* Address bar */
QLineEdit {
    background: #141828;
    border: 1px solid #2e3248;
    border-radius: 4px;
    color: #94a3b8;
    font-size: 11px;
    padding: 4px 8px;
    selection-background-color: #4f46e5;
}
QLineEdit:focus { border-color: #4f46e5; color: #e2e8f0; }

/* Buttons */
QPushButton {
    background: #1a1f35;
    border: 1px solid #2e3248;
    border-radius: 4px;
    color: #94a3b8;
    font-size: 11px;
    padding: 3px 10px;
}
QPushButton:hover  { background: #252b45; color: #e2e8f0; }
QPushButton:pressed { background: #4f46e5; }

/* Toolbar */
#toolbar {
    background: #111427;
    border-bottom: 1px solid #1e2236;
}

/* Status bar */
#statusBar {
    background: #080a14;
    border-top: 1px solid #1e2236;
    color: #475569;
    font-size: 10px;
    padding: 2px 8px;
}

/* Attach button */
QPushButton#attachBtn {
    background: #4f46e5;
    border: none;
    color: white;
    font-weight: 700;
    font-size: 12px;
    padding: 6px 16px;
    border-radius: 5px;
}
QPushButton#attachBtn:hover    { background: #6366f1; }
QPushButton#attachBtn:disabled { background: #1e2236; color: #475569; }

/* Context menu */
QMenu {
    background: #141828;
    border: 1px solid #2e3248;
    color: #cbd5e1;
    padding: 4px;
}
QMenu::item { padding: 6px 24px 6px 12px; border-radius: 3px; }
QMenu::item:selected { background: #2d3561; }
QMenu::separator { height: 1px; background: #1e2236; margin: 3px 0; }
"""


class FileManagerPanel(QWidget):
    """
    Full-featured file manager panel.
    Signal `file_attach_requested(str)` fires when user attaches a file to chat.
    """
    file_attach_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(520)
        self.setObjectName("fileManagerPanel")
        self.setStyleSheet(_PANEL_STYLE)

        self._clipboard_paths: list[str] = []
        self._clipboard_op: str = ''          # 'copy' or 'cut'

        self._build_ui()
        self._navigate(OUTPUT_DIR)   # open to Output folder on launch

    # ── UI construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet("background:#111427; border-bottom:1px solid #1e2236;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(10, 7, 8, 7)
        title = QLabel("📁  File Manager")
        title.setStyleSheet("color:#e2e8f0; font-weight:700; font-size:13px;")
        h_lay.addWidget(title)
        h_lay.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "background:transparent; border:none; color:#475569; font-size:13px;"
        )
        close_btn.clicked.connect(self.hide)
        h_lay.addWidget(close_btn)
        root.addWidget(header)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(8, 5, 8, 5)
        tb.setSpacing(4)

        def _tb(text, tip, fn):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFixedHeight(26)
            b.clicked.connect(fn)
            tb.addWidget(b)
            return b

        self._back_btn = _tb("←", "Back", self._go_back)
        self._up_btn   = _tb("↑", "Go up (Backspace)", self._go_up)
        tb.addWidget(self._mk_sep())

        self._addr = QLineEdit()
        self._addr.setPlaceholderText("Path…")
        self._addr.returnPressed.connect(
            lambda: self._navigate(Path(self._addr.text()))
        )
        tb.addWidget(self._addr, stretch=1)

        tb.addWidget(self._mk_sep())
        _tb("📁+", "New folder (Ctrl+Shift+N)", self._new_folder)
        _tb("✂", "Cut (Ctrl+X)",  self._cut)
        _tb("📋", "Copy (Ctrl+C)", self._copy)
        _tb("📌", "Paste (Ctrl+V)", self._paste)
        _tb("🗑", "Delete (Del)",  self._delete)
        _tb("✏", "Rename (F2)",   self._rename)
        root.addWidget(toolbar)

        # ── Splitter: quick-access | file tree ────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(
            "QSplitter::handle { background: #1e2236; }"
        )

        # Quick-access sidebar
        self._quick = QListWidget()
        self._quick.setFixedWidth(148)

        # ── Pinned section header ─────────────────────────────────────────
        pin_hdr = QListWidgetItem(" PINNED")
        pin_hdr.setFlags(Qt.ItemFlag.NoItemFlags)   # not clickable
        pin_hdr.setForeground(QColor('#4f46e5'))
        font = QFont('Segoe UI', 8)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        pin_hdr.setFont(font)
        self._quick.addItem(pin_hdr)

        for label, folder in _PINNED:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(folder))
            item.setForeground(QColor('#818cf8'))
            f2 = QFont('Segoe UI', 11)
            f2.setBold(True)
            item.setFont(f2)
            item.setBackground(QColor('#0f1030'))
            self._quick.addItem(item)

        # ── Separator ─────────────────────────────────────────────────────
        sep = QListWidgetItem("─" * 14)
        sep.setFlags(Qt.ItemFlag.NoItemFlags)
        sep.setForeground(QColor('#1e2236'))
        sep.setFont(QFont('Segoe UI', 7))
        self._quick.addItem(sep)

        # ── Regular folders ───────────────────────────────────────────────
        places_hdr = QListWidgetItem(" PLACES")
        places_hdr.setFlags(Qt.ItemFlag.NoItemFlags)
        places_hdr.setForeground(QColor('#4f46e5'))
        places_hdr.setFont(font)
        self._quick.addItem(places_hdr)

        for label, folder in _QUICK:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(folder))
            self._quick.addItem(item)

        self._quick.itemClicked.connect(
            lambda i: self._navigate(Path(i.data(Qt.ItemDataRole.UserRole)))
                      if i.data(Qt.ItemDataRole.UserRole) else None
        )
        splitter.addWidget(self._quick)

        # File tree using QFileSystemModel
        self._model = QFileSystemModel()
        self._model.setRootPath('')
        self._model.setFilter(
            QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        )

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self._tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        # Drag & drop — native OS-level file move/copy via model
        self._tree.setDragEnabled(True)
        self._tree.setAcceptDrops(True)
        self._tree.setDropIndicatorShown(True)
        self._tree.setDragDropMode(
            QAbstractItemView.DragDropMode.DragDrop
        )
        self._tree.setDefaultDropAction(Qt.DropAction.MoveAction)

        # Hide unneeded columns (keep Name, Size, Type, Date)
        self._tree.setColumnWidth(0, 240)
        self._tree.setColumnWidth(1, 70)
        self._tree.setColumnWidth(2, 80)
        self._tree.setColumnWidth(3, 120)
        self._tree.header().setStretchLastSection(False)

        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.selectionModel().selectionChanged.connect(self._on_selection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)

        splitter.addWidget(self._tree)
        splitter.setSizes([148, 500])
        root.addWidget(splitter, stretch=1)

        # ── Bottom action bar ─────────────────────────────────────────────────
        bottom = QWidget()
        bottom.setStyleSheet("background:#0d0f1e; border-top:1px solid #1e2236;")
        b_lay = QHBoxLayout(bottom)
        b_lay.setContentsMargins(8, 6, 8, 6)
        b_lay.setSpacing(8)

        self._status = QLabel("Ready")
        self._status.setObjectName("statusBar")
        self._status.setStyleSheet("color:#475569; font-size:10px;")
        b_lay.addWidget(self._status, stretch=1)

        self._attach_btn = QPushButton("📎  Attach to Chat")
        self._attach_btn.setObjectName("attachBtn")
        self._attach_btn.setFixedHeight(30)
        self._attach_btn.setEnabled(False)
        self._attach_btn.clicked.connect(self._attach)
        b_lay.addWidget(self._attach_btn)

        root.addWidget(bottom)

        # ── Keyboard shortcuts ────────────────────────────────────────────────
        self._setup_shortcuts()

        # History for Back button
        self._history: list[Path] = []
        self._current: Path = Path.home()

    def _mk_sep(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color:#1e2236;")
        sep.setFixedWidth(1)
        return sep

    def _setup_shortcuts(self):
        def _sh(seq, fn):
            s = QShortcut(QKeySequence(seq), self)
            s.activated.connect(fn)

        _sh("Ctrl+C",       self._copy)
        _sh("Ctrl+X",       self._cut)
        _sh("Ctrl+V",       self._paste)
        _sh("Delete",       self._delete)
        _sh("F2",           self._rename)
        _sh("Ctrl+A",       self._select_all)
        _sh("Backspace",    self._go_up)
        _sh("Ctrl+Shift+N", self._new_folder)
        _sh("Alt+Left",     self._go_back)

    # ── Navigation ────────────────────────────────────────────────────────────
    def _navigate(self, path: Path):
        try:
            path = path.expanduser().resolve()
            if not path.is_dir():
                path = path.parent
            if path == self._current:
                return
            self._history.append(self._current)
            self._current = path
            idx = self._model.index(str(path))
            self._tree.setRootIndex(idx)
            self._addr.setText(str(path))
            self._status.setText(f"  {str(path)}")
        except Exception as e:
            self._status.setText(f"  Error: {e}")

    def _go_up(self):
        self._navigate(self._current.parent)

    def _go_back(self):
        if self._history:
            prev = self._history.pop()
            self._current = Path('')     # prevent duplicate append
            self._navigate(prev)

    def _on_double_click(self, index: QModelIndex):
        path = Path(self._model.filePath(index))
        if path.is_dir():
            self._navigate(path)
        # else: open with OS default
        else:
            os.startfile(str(path))

    # ── Selection ─────────────────────────────────────────────────────────────
    def _selected_paths(self) -> list[Path]:
        return [
            Path(self._model.filePath(i))
            for i in self._tree.selectedIndexes()
            if i.column() == 0
        ]

    def _on_selection(self):
        paths = self._selected_paths()
        files = [p for p in paths if p.is_file()]
        if not paths:
            self._status.setText(f"  {str(self._current)}")
            self._attach_btn.setEnabled(False)
        else:
            total_size = sum(
                p.stat().st_size for p in paths if p.is_file()
            )
            sz = f"{total_size // 1024} KB" if total_size >= 1024 else f"{total_size} B"
            self._status.setText(
                f"  {len(paths)} selected  |  {sz}"
            )
            self._attach_btn.setEnabled(bool(files))

    def _select_all(self):
        self._tree.selectAll()

    # ── File operations ───────────────────────────────────────────────────────
    def _copy(self):
        paths = self._selected_paths()
        if not paths:
            return
        self._clipboard_paths = [str(p) for p in paths]
        self._clipboard_op    = 'copy'
        # Also set OS clipboard so you can paste into Explorer
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
        QApplication.clipboard().setMimeData(mime)
        self._status.setText(f"  Copied {len(paths)} item(s) — Ctrl+V to paste")

    def _cut(self):
        paths = self._selected_paths()
        if not paths:
            return
        self._clipboard_paths = [str(p) for p in paths]
        self._clipboard_op    = 'cut'
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
        QApplication.clipboard().setMimeData(mime)
        self._status.setText(f"  Cut {len(paths)} item(s) — Ctrl+V to paste")

    def _paste(self):
        # Prefer internal clipboard; fall back to OS clipboard URLs
        if self._clipboard_paths:
            paths = self._clipboard_paths
            op    = self._clipboard_op
        else:
            mime = QApplication.clipboard().mimeData()
            if mime.hasUrls():
                paths = [u.toLocalFile() for u in mime.urls()]
                op    = 'copy'
            else:
                return

        dest = self._current
        errors = []
        for src_str in paths:
            src = Path(src_str)
            tgt = dest / src.name
            # Avoid overwriting — add suffix
            counter = 1
            while tgt.exists():
                tgt = dest / f"{src.stem}_copy{counter}{src.suffix}"
                counter += 1
            try:
                if op == 'cut':
                    shutil.move(str(src), str(tgt))
                else:
                    if src.is_dir():
                        shutil.copytree(str(src), str(tgt))
                    else:
                        shutil.copy2(str(src), str(tgt))
            except Exception as e:
                errors.append(f"{src.name}: {e}")

        if op == 'cut':
            self._clipboard_paths.clear()
            self._clipboard_op = ''

        if errors:
            QMessageBox.warning(self, "Paste errors", "\n".join(errors))
        else:
            self._status.setText(f"  Pasted {len(paths)} item(s) to {dest.name}")

    def _delete(self):
        paths = self._selected_paths()
        if not paths:
            return
        names = ', '.join(p.name for p in paths[:3])
        if len(paths) > 3:
            names += f" and {len(paths)-3} more"
        reply = QMessageBox.question(
            self, "Delete",
            f"Permanently delete {names}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        errors = []
        for p in paths:
            try:
                if p.is_dir():
                    shutil.rmtree(str(p))
                else:
                    p.unlink()
            except Exception as e:
                errors.append(f"{p.name}: {e}")
        if errors:
            QMessageBox.warning(self, "Delete errors", "\n".join(errors))
        else:
            self._status.setText(f"  Deleted {len(paths)} item(s)")

    def _rename(self):
        paths = self._selected_paths()
        if not paths:
            return
        p = paths[0]
        new_name, ok = QInputDialog.getText(
            self, "Rename", f"New name for '{p.name}':", text=p.name
        )
        if ok and new_name.strip() and new_name != p.name:
            try:
                p.rename(p.parent / new_name.strip())
                self._status.setText(f"  Renamed to {new_name.strip()}")
            except Exception as e:
                QMessageBox.warning(self, "Rename error", str(e))

    def _new_folder(self):
        name, ok = QInputDialog.getText(
            self, "New Folder", "Folder name:", text="New Folder"
        )
        if ok and name.strip():
            try:
                (self._current / name.strip()).mkdir(parents=True, exist_ok=False)
                self._status.setText(f"  Created folder: {name.strip()}")
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    # ── Context menu ──────────────────────────────────────────────────────────
    def _show_context_menu(self, pos):
        paths = self._selected_paths()
        menu  = QMenu(self)

        if paths:
            menu.addAction("📎  Attach to Chat",  self._attach)
            menu.addSeparator()
            menu.addAction("✂  Cut",    self._cut)
            menu.addAction("📋  Copy",  self._copy)
        menu.addAction("📌  Paste",    self._paste)
        menu.addSeparator()
        if paths:
            menu.addAction("✏  Rename", self._rename)
            menu.addAction("🗑  Delete", self._delete)
            menu.addSeparator()
            if len(paths) == 1 and paths[0].is_file():
                menu.addAction("🚀  Open",  lambda: os.startfile(str(paths[0])))
                menu.addAction("📂  Show in Explorer",
                               lambda: os.startfile(str(paths[0].parent)))
        menu.addSeparator()
        menu.addAction("📁+  New Folder", self._new_folder)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    # ── Attach to chat ────────────────────────────────────────────────────────
    def _attach(self):
        paths = [p for p in self._selected_paths() if p.is_file()]
        for p in paths:
            self.file_attach_requested.emit(str(p))
        if paths:
            self._status.setText(
                f"  ✅ Attached: {', '.join(p.name for p in paths)}"
            )

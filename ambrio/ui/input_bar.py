# ambrio/ui/input_bar.py
"""
Multi-Format Input Bar for Ambrio.

Supported inputs (video excluded):
  ✅ Text       — typed messages
  ✅ Images     — JPG, PNG, GIF, BMP, WEBP (preview shown inline)
  ✅ PDFs       — drag-drop or browse, sent to doc_read tool
  ✅ Word docs  — .docx, .doc → doc_read
  ✅ Excel      — .xlsx, .xls, .csv → doc_read
  ✅ Audio      — .mp3, .wav, .m4a, .ogg (path sent for Whisper/future)
  ✅ Code files — .py, .js, .ts, .java, .cpp etc → file_read
  ✅ Text files — .txt, .md, .log, .json, .xml → file_read
  ✅ Drag & drop anywhere on the input bar
  ✅ Paste from clipboard (Ctrl+V images)
  ✅ Attach button → file browser
  ✅ Multi-file in one message
"""
import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTextEdit, QPushButton,
    QLabel, QFileDialog, QScrollArea, QSizePolicy, QFrame
)
from PyQt6.QtCore    import Qt, pyqtSignal, QMimeData, QUrl
from PyQt6.QtGui     import (
    QKeyEvent, QDragEnterEvent, QDropEvent, QPixmap, QColor,
    QPainter, QPainterPath, QClipboard
)

# ── File type categorisation ──────────────────────────────────────────────────
_IMAGE_EXTS   = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.ico', '.svg'}
_DOC_EXTS     = {'.pdf', '.docx', '.doc', '.pptx', '.ppt', '.odt'}
_SHEET_EXTS   = {'.xlsx', '.xls', '.csv', '.ods'}
_AUDIO_EXTS   = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma'}
_CODE_EXTS    = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.cs',
                 '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.r', '.sql', '.sh',
                 '.bat', '.ps1', '.yaml', '.yml', '.toml', '.ini', '.cfg'}
_TEXT_EXTS    = {'.txt', '.md', '.log', '.json', '.xml', '.html', '.htm', '.rst', '.env'}
_VIDEO_EXTS   = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm'}  # blocked

_ALL_SUPPORTED = _IMAGE_EXTS | _DOC_EXTS | _SHEET_EXTS | _AUDIO_EXTS | _CODE_EXTS | _TEXT_EXTS

_TYPE_ICONS = {
    'image':  '🖼',
    'pdf':    '📄',
    'doc':    '📝',
    'sheet':  '📊',
    'audio':  '🎵',
    'code':   '💻',
    'text':   '📃',
    'other':  '📎',
}

_TYPE_COLORS = {
    'image':  '#3B82F6',
    'pdf':    '#EF4444',
    'doc':    '#2563EB',
    'sheet':  '#16A34A',
    'audio':  '#9333EA',
    'code':   '#F59E0B',
    'text':   '#6B7280',
    'other':  '#64748B',
}


def _classify(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in _IMAGE_EXTS:   return 'image'
    if ext == '.pdf':         return 'pdf'
    if ext in _DOC_EXTS:     return 'doc'
    if ext in _SHEET_EXTS:   return 'sheet'
    if ext in _AUDIO_EXTS:   return 'audio'
    if ext in _CODE_EXTS:    return 'code'
    if ext in _TEXT_EXTS:    return 'text'
    return 'other'


# ── File chip widget ──────────────────────────────────────────────────────────
class FileChip(QWidget):
    """Compact removable chip showing an attached file."""
    removed = pyqtSignal(str)  # emits file path

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        kind  = _classify(file_path)
        icon  = _TYPE_ICONS.get(kind, '📎')
        color = _TYPE_COLORS.get(kind, '#64748B')
        name  = Path(file_path).name
        short = name if len(name) <= 22 else name[:10] + '…' + name[-8:]

        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 4, 0)
        lay.setSpacing(6)

        # Thumbnail for images, icon for others
        if kind == 'image':
            pix_label = QLabel()
            pix = QPixmap(file_path)
            if not pix.isNull():
                pix = pix.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                pix_label.setPixmap(pix)
            else:
                pix_label.setText(icon)
            pix_label.setFixedSize(28, 28)
            lay.addWidget(pix_label)
        else:
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet("font-size: 16px;")
            lay.addWidget(icon_lbl)

        name_lbl = QLabel(short)
        name_lbl.setToolTip(file_path)
        name_lbl.setStyleSheet(f"color: #F5F5F4; font-size: 12px; font-weight: 500;")
        lay.addWidget(name_lbl)

        rm_btn = QPushButton("✕")
        rm_btn.setFixedSize(18, 18)
        rm_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #A8A29E; font-size: 11px; }"
            "QPushButton:hover { color: #EF4444; }"
        )
        rm_btn.clicked.connect(lambda: self.removed.emit(self.file_path))
        lay.addWidget(rm_btn)

        self.setStyleSheet(
            f"FileChip {{ background: {color}22; border: 1px solid {color}55; "
            f"border-radius: 6px; }}"
        )


# ── Attachments strip ─────────────────────────────────────────────────────────
class AttachmentStrip(QWidget):
    """Horizontal scrollable strip of FileChip widgets."""
    files_changed = pyqtSignal(list)  # emits updated file list

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = []
        self.setVisible(False)
        self.setFixedHeight(44)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("background: transparent;")

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._chip_lay  = QHBoxLayout(self._container)
        self._chip_lay.setContentsMargins(0, 0, 0, 0)
        self._chip_lay.setSpacing(6)
        self._chip_lay.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

    def add_file(self, path: str) -> bool:
        """Add file to strip. Returns False if already added or unsupported."""
        if path in self._files:
            return False
        ext = Path(path).suffix.lower()
        if ext in _VIDEO_EXTS:
            return False  # skip videos
        if ext and ext not in _ALL_SUPPORTED:
            # allow unknown extensions — file_read will try anyway
            pass

        chip = FileChip(path)
        chip.removed.connect(self._remove_file)
        # Insert before the stretch
        self._chip_lay.insertWidget(self._chip_lay.count() - 1, chip)
        self._files.append(path)
        self.setVisible(True)
        self.files_changed.emit(self._files.copy())
        return True

    def _remove_file(self, path: str):
        self._files.remove(path)
        # Rebuild chips
        for i in reversed(range(self._chip_lay.count())):
            w = self._chip_lay.itemAt(i).widget()
            if w and isinstance(w, FileChip):
                self._chip_lay.removeWidget(w)
                w.deleteLater()
        for f in self._files:
            chip = FileChip(f)
            chip.removed.connect(self._remove_file)
            self._chip_lay.insertWidget(self._chip_lay.count() - 1, chip)
        self.setVisible(bool(self._files))
        self.files_changed.emit(self._files.copy())

    def get_files(self) -> list[str]:
        return self._files.copy()

    def clear_files(self):
        self._files.clear()
        for i in reversed(range(self._chip_lay.count())):
            w = self._chip_lay.itemAt(i).widget()
            if w and isinstance(w, FileChip):
                self._chip_lay.removeWidget(w)
                w.deleteLater()
        self.setVisible(False)
        self.files_changed.emit([])


# ── Text edit with drag-drop + paste ─────────────────────────────────────────
class _MultiInputEdit(QTextEdit):
    submitted   = pyqtSignal()
    files_added = pyqtSignal(list)  # list of paths

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def keyPressEvent(self, e: QKeyEvent):
        no_shift = not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and no_shift:
            self.submitted.emit()
        else:
            super().keyPressEvent(e)

    # ── Drag & Drop ──────────────────────────────────────────────────────────
    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls() or e.mimeData().hasImage():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dropEvent(self, e: QDropEvent):
        paths = []
        if e.mimeData().hasUrls():
            for url in e.mimeData().urls():
                if url.isLocalFile():
                    paths.append(url.toLocalFile())
        if paths:
            self.files_added.emit(paths)
        elif e.mimeData().hasImage():
            # Handle dropped image data (save temp file)
            self._save_clipboard_image(e.mimeData())
        else:
            super().dropEvent(e)

    # ── Clipboard paste (Ctrl+V image) ───────────────────────────────────────
    def insertFromMimeData(self, source: QMimeData):
        if source.hasImage():
            self._save_clipboard_image(source)
        elif source.hasUrls():
            paths = [u.toLocalFile() for u in source.urls() if u.isLocalFile()]
            if paths:
                self.files_added.emit(paths)
                return
        super().insertFromMimeData(source)

    def _save_clipboard_image(self, mime: QMimeData):
        """Save clipboard image to temp file and emit as attachment."""
        import tempfile
        img = mime.imageData()
        if img and not img.isNull():
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False,
                                              prefix='ambrio_paste_')
            img.save(tmp.name, 'PNG')
            self.files_added.emit([tmp.name])


# ── Main InputBar ─────────────────────────────────────────────────────────────
class InputBar(QWidget):
    """
    Multi-format input bar.
    Emits submitted(text, files) where files is a list of attached file paths.
    """
    submitted = pyqtSignal(str, list)   # text, [file_paths]

    # Supported file filter for QFileDialog
    _FILE_FILTER = (
        "All Supported ("
        "*.jpg *.jpeg *.png *.gif *.bmp *.webp *.tiff "
        "*.pdf *.docx *.doc *.pptx *.ppt "
        "*.xlsx *.xls *.csv "
        "*.mp3 *.wav *.m4a *.ogg *.flac *.aac "
        "*.py *.js *.ts *.java *.c *.cpp *.cs *.go *.rs *.sql *.sh *.ps1 "
        "*.txt *.md *.log *.json *.xml *.html *.yaml *.toml "
        ");;"
        "Images (*.jpg *.jpeg *.png *.gif *.bmp *.webp *.tiff);;"
        "Documents (*.pdf *.docx *.doc *.xlsx *.xls *.csv);;"
        "Code (*.py *.js *.ts *.java *.c *.cpp *.go *.rs *.sql *.sh);;"
        "Audio (*.mp3 *.wav *.m4a *.ogg *.flac);;"
        "Text (*.txt *.md *.log *.json *.xml *.html);;"
        "All Files (*.*)"
    )

    def __init__(self):
        super().__init__()
        self._attached_files: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Attachment strip ─────────────────────────────────────────────────
        self._strip = AttachmentStrip()
        self._strip.files_changed.connect(self._on_files_changed)
        outer.addWidget(self._strip)

        # ── Drop zone hint (shown when dragging) ─────────────────────────────
        self._drop_hint = QLabel("Drop files here — images, PDFs, docs, code, audio")
        self._drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_hint.setVisible(False)
        self._drop_hint.setStyleSheet(
            "color: #CA8A04; font-size: 12px; font-style: italic; padding: 4px;"
        )
        outer.addWidget(self._drop_hint)

        # ── Input row ────────────────────────────────────────────────────────
        row = QWidget()
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(12, 8, 12, 12)
        row_lay.setSpacing(8)

        # Attach button
        self._attach_btn = QPushButton("📎")
        self._attach_btn.setObjectName("attachBtn")
        self._attach_btn.setFixedSize(44, 44)
        self._attach_btn.setToolTip("Attach file (or drag & drop)")
        self._attach_btn.clicked.connect(self._browse_files)
        self._attach_btn.setStyleSheet(
            "QPushButton#attachBtn {"
            "  background: #1C1917; border: 1px solid #3D3836;"
            "  border-radius: 8px; font-size: 18px; color: #A8A29E;"
            "}"
            "QPushButton#attachBtn:hover {"
            "  border-color: #CA8A04; color: #CA8A04; background: #CA8A0411;"
            "}"
        )
        row_lay.addWidget(self._attach_btn)

        # Text input
        self._input = _MultiInputEdit()
        self._input.setObjectName("chatInput")
        self._input.setPlaceholderText(
            "Message Ambrio…  (Shift+Enter for newline, drag files or Ctrl+V to attach)"
        )
        self._input.setMaximumHeight(120)
        self._input.setMinimumHeight(50)
        self._input.submitted.connect(self._on_submit)
        self._input.files_added.connect(self._add_files)
        row_lay.addWidget(self._input, stretch=1)

        # Send button
        self._btn = QPushButton("Send ↑")
        self._btn.setObjectName("sendBtn")
        self._btn.setFixedWidth(80)
        self._btn.setFixedHeight(44)
        self._btn.clicked.connect(self._on_submit)
        row_lay.addWidget(self._btn)

        outer.addWidget(row)

    # ── File handling ─────────────────────────────────────────────────────────
    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Attach Files", "", self._FILE_FILTER
        )
        if paths:
            self._add_files(paths)

    def _add_files(self, paths: list[str]):
        for p in paths:
            ext = Path(p).suffix.lower()
            if ext in _VIDEO_EXTS:
                continue  # skip videos per user request
            self._strip.add_file(p)

    def _on_files_changed(self, files: list[str]):
        self._attached_files = files

    # ── Submit ────────────────────────────────────────────────────────────────
    def _on_submit(self):
        text  = self._input.toPlainText().strip()
        files = self._attached_files.copy()

        if not text and not files:
            return

        # Auto-generate text if only files attached with no message
        if not text and files:
            names = [Path(f).name for f in files]
            text  = f"Please analyze: {', '.join(names)}"

        self._input.clear()
        self._strip.clear_files()
        self.submitted.emit(text, files)

    def set_enabled(self, enabled: bool):
        self._input.setEnabled(enabled)
        self._btn.setEnabled(enabled)
        self._attach_btn.setEnabled(enabled)
        if enabled:
            self._input.setFocus()

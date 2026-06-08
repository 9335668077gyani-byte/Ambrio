# ambrio/ui/main_window.py
import uuid
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QMessageBox, QFrame
)
from PyQt6.QtGui import QKeySequence, QShortcut
from .chat_widget      import ChatWidget
from .input_bar        import InputBar
from .sidebar          import Sidebar
from .settings_dialog  import SettingsDialog
from .file_manager     import FileManagerPanel
from .ipc.qt_zmq_bridge    import ZmqBridge
from .ipc.message_protocol import Frame, MsgType


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("⚡ Ambrio — Local AI")
        self.resize(1280, 820)
        self.setMinimumSize(900, 600)

        self._session_id = str(uuid.uuid4())

        # ── ZMQ bridge (runs on a QThread) ───────────────────────────────────
        self._bridge = ZmqBridge()
        self._bridge.token_received.connect(self._on_token)
        self._bridge.done_received.connect(self._on_done)
        self._bridge.tool_call_gate.connect(self._on_tool_call)
        self._bridge.error_received.connect(self._on_error)
        self._bridge.start()

        # ── Layout ────────────────────────────────────────────────────────────
        root  = QWidget()
        self.setCentralWidget(root)
        h_lay = QHBoxLayout(root)
        h_lay.setContentsMargins(0, 0, 0, 0)
        h_lay.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.new_session.connect(self._set_session)
        self._sidebar.session_selected.connect(self._set_session)
        self._sidebar.settings_clicked.connect(self._open_settings)
        h_lay.addWidget(self._sidebar)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet("color: #2e3248;")
        h_lay.addWidget(div)

        # Right pane: chat + input
        right = QWidget()
        v_lay = QVBoxLayout(right)
        v_lay.setContentsMargins(0, 0, 0, 0)
        v_lay.setSpacing(0)

        self._chat  = ChatWidget()
        self._input = InputBar()
        self._input.submitted.connect(self._on_send)   # (text, files)
        v_lay.addWidget(self._chat, stretch=1)

        # Subtle divider above input
        h_div = QFrame()
        h_div.setFrameShape(QFrame.Shape.HLine)
        h_div.setStyleSheet("color: #2e3248;")
        v_lay.addWidget(h_div)
        v_lay.addWidget(self._input)

        # Status bar — shows active model at bottom
        from PyQt6.QtWidgets import QLabel
        self._status_bar = QLabel("  ⚡ Ambrio ready — model: loading...")
        self._status_bar.setStyleSheet(
            "background: #0f111a; color: #475569; font-size: 10px; "
            "font-family: 'Consolas', monospace; padding: 3px 12px; "
            "border-top: 1px solid #1e2236;"
        )
        v_lay.addWidget(self._status_bar)

        h_lay.addWidget(right, stretch=1)

        # ── File Manager Panel (right side, hidden by default) ────────────────
        self._file_mgr = FileManagerPanel()
        self._file_mgr.file_attach_requested.connect(self._attach_from_file_manager)
        self._file_mgr.hide()
        h_lay.addWidget(self._file_mgr)

        # Connect 📁 button on input bar to toggle file manager
        self._input.connect_file_manager(self._toggle_file_manager)

        # Create the default session in the sidebar
        self._sidebar.add_session(self._session_id)

        # Keyboard shortcuts
        shortcut = QShortcut(QKeySequence("Ctrl+,"), self)
        shortcut.activated.connect(self._open_settings)
        fm_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        fm_shortcut.activated.connect(self._toggle_file_manager)

    # ── Settings ──────────────────────────────────────────────────────────────
    def _open_settings(self):
        dlg = SettingsDialog(self)
        dlg.keys_saved.connect(self._reload_router)
        dlg.exec()

    # ── File Manager ──────────────────────────────────────────────────────────
    def _toggle_file_manager(self):
        """Toggle the file manager panel (Ctrl+E)."""
        if self._file_mgr.isVisible():
            self._file_mgr.hide()
        else:
            self._file_mgr.show()

    def _attach_from_file_manager(self, path: str):
        """Called when user clicks 'Attach to Chat' in file manager."""
        self._input.attach_file(path)

    def _reload_router(self):
        """Hot-reload the ModelRouter with new keys from .env — no restart needed."""
        try:
            # Reload config module so it picks up new .env values
            import importlib
            import ambrio.config as cfg
            importlib.reload(cfg)

            from ambrio.config import PROVIDER_KEYS
            from ambrio.router.model_router import ModelRouter

            # Send a special internal message to the router service to reinitialize
            # For now, show a notice — full hot-reload is Phase 7c
            self._chat.add_system_notice(
                "✓ API keys saved. Restart Ambrio to activate new providers."
            )
        except Exception as e:
            self._chat.add_system_notice(f"Settings reload error: {e}")
    # ── Routing ───────────────────────────────────────────────────────────────
    def _set_session(self, sid: str):
        self._session_id = sid

    # ── Send / receive ──────────────────────────────────────────────────────────────
    def _on_send(self, text: str, files: list = None):
        """Handle text + optional file attachments.
        Files are read synchronously here — content injected into the prompt.
        """
        from pathlib import Path
        files = files or []

        # ── Build display text shown in chat bubble ───────────────────────────
        display_text = text or ""
        if files:
            for f in files:
                display_text += f"\n📎 {Path(f).name}"

        # ── Read each file synchronously and inject real content ──────────────
        injected_blocks = []
        if files:
            from ambrio.router.tools.doc_tool import (
                _read_pdf, _read_docx, _read_xlsx, _read_image_ocr
            )
            for f in files:
                p = Path(f)
                ext = p.suffix.lower()
                try:
                    if not p.exists():
                        injected_blocks.append(
                            f"[FILE: {p.name}]\nError: File not found at {f}"
                        )
                        continue

                    if ext == '.pdf':
                        content = _read_pdf(p)
                    elif ext in ('.docx', '.doc'):
                        content = _read_docx(p)
                    elif ext in ('.xlsx', '.xls'):
                        content = _read_xlsx(p)
                    elif ext == '.csv':
                        content = p.read_text(encoding='utf-8', errors='replace')
                    elif ext in ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp', '.gif', '.ico', '.svg'):
                        # ✅ Images: never read as text — pass path only
                        # The model will call doc_convert("path","pdf") or similar
                        size_kb = round(p.stat().st_size / 1024, 1)
                        injected_blocks.append(
                            f"[IMAGE FILE: {p.name} | path: {f} | size: {size_kb} KB]\n"
                            f"This is an image file. To convert it, call: doc_convert(\"{f}\", \"pdf\")\n"
                            f"To describe its contents you would need vision capability."
                        )
                        continue
                    else:
                        # Try reading as text; if it looks binary, skip content
                        try:
                            content = p.read_text(encoding='utf-8', errors='strict')
                        except (UnicodeDecodeError, ValueError):
                            size_kb = round(p.stat().st_size / 1024, 1)
                            injected_blocks.append(
                                f"[BINARY FILE: {p.name} | path: {f} | size: {size_kb} KB]\n"
                                f"This is a binary file. To convert it call: doc_convert(\"{f}\", \"pdf\")"
                            )
                            continue

                    # Truncate to 6000 chars to stay within context budget
                    truncated = len(content) > 6000
                    snippet   = content[:6000]
                    trunc_note = " [truncated to 6000 chars]" if truncated else ""
                    injected_blocks.append(
                        f"[FILE: {p.name} | path: {f} | type: {ext}{trunc_note}]\n{snippet}"
                    )
                except Exception as e:
                    injected_blocks.append(
                        f"[FILE: {p.name} | path: {f}]\nCould not read file: {e}"
                    )


        # ── Compose final message sent to router ──────────────────────────────
        parts = []
        if injected_blocks:
            parts.append(
                "The user attached the following file(s).\n"
                "- To READ/SUMMARIZE: use the content shown below.\n"
                "- To EDIT and SAVE: make your changes, then call "
                "file_write(\"<path>\", \"<full edited content>\") "
                "using the exact path shown in the FILE header.\n\n"
                + "\n\n---\n\n".join(injected_blocks)
            )
        if text:
            parts.append(text)
        full_text = "\n\n".join(parts) if parts else (text or "")

        # ── Send to UI and router ─────────────────────────────────────────────
        self._chat.add_user_message(display_text)
        self._chat.begin_assistant_message()
        self._input.set_enabled(False)
        self._bridge.send(Frame(
            session_id=self._session_id,
            type=MsgType.CHAT_REQUEST,
            payload={"content": full_text}
        ))

    def _on_token(self, session_id: str, token: str):
        if session_id == self._session_id:
            self._chat.append_token(token)

    def _on_done(self, session_id: str, payload: dict):
        if session_id == self._session_id:
            self._chat.finalize_assistant_message(meta=payload)
            self._input.set_enabled(True)
            # Update status bar with last used model
            model    = payload.get("model", "")
            provider = payload.get("provider", "")
            tokens   = payload.get("tokens",  0)
            elapsed  = payload.get("elapsed", 0.0)
            short_model = model.split("/", 1)[-1] if "/" in model else model
            if model:
                self._status_bar.setText(
                    f"  ⚡ {provider} · {short_model} · last reply: {tokens} tok · {elapsed}s"
                )

    def _on_tool_call(self, session_id: str, payload: dict):
        """Human-in-the-loop approval gate for tool execution."""
        fn   = payload.get("function", payload)   # handle both formats
        name = fn.get("name", "unknown_tool")
        args = fn.get("arguments", "{}")

        box = QMessageBox(self)
        box.setWindowTitle("🔧 Tool Approval Required")
        box.setText(
            f"<b>Ambrio wants to call:</b><br><br>"
            f"<code>{name}</code><br><br>"
            f"<b>Arguments:</b><br><pre>{args}</pre>"
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)

        if box.exec() == QMessageBox.StandardButton.Yes:
            self._bridge.send(Frame(
                session_id=session_id,
                type=MsgType.TOOL_RESULT,
                payload={
                    "tool_name": name,
                    "tool_args": args if isinstance(args, dict) else {}
                }
            ))
        else:
            self._chat.add_system_notice(f"Tool call '{name}' was rejected.")
            self._chat.finalize_assistant_message()
            self._input.set_enabled(True)

    def _on_error(self, session_id: str, msg: str):
        if session_id == self._session_id:
            self._chat.finalize_assistant_message()
            self._chat.add_system_notice(f"Error: {msg}")
            self._input.set_enabled(True)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self._bridge.stop()
        self._bridge.wait(2000)
        super().closeEvent(event)

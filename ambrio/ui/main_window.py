# ambrio/ui/main_window.py
import uuid
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QMessageBox, QFrame
)
from .chat_widget   import ChatWidget
from .input_bar     import InputBar
from .sidebar       import Sidebar
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
        self._input.submitted.connect(self._on_send)
        v_lay.addWidget(self._chat, stretch=1)

        # Subtle divider above input
        h_div = QFrame()
        h_div.setFrameShape(QFrame.Shape.HLine)
        h_div.setStyleSheet("color: #2e3248;")
        v_lay.addWidget(h_div)
        v_lay.addWidget(self._input)
        h_lay.addWidget(right, stretch=1)

        # Create the default session in the sidebar
        self._sidebar.add_session(self._session_id)

    # ── Routing ───────────────────────────────────────────────────────────────
    def _set_session(self, sid: str):
        self._session_id = sid

    # ── Send / receive ────────────────────────────────────────────────────────
    def _on_send(self, text: str):
        self._chat.add_user_message(text)
        self._chat.begin_assistant_message()
        self._input.set_enabled(False)
        self._bridge.send(Frame(
            session_id=self._session_id,
            type=MsgType.CHAT_REQUEST,
            payload={"content": text}
        ))

    def _on_token(self, session_id: str, token: str):
        if session_id == self._session_id:
            self._chat.append_token(token)

    def _on_done(self, session_id: str):
        if session_id == self._session_id:
            self._chat.finalize_assistant_message()
            self._input.set_enabled(True)

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

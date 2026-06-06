# ambrio/ui/ipc/qt_zmq_bridge.py
import zmq, zmq.asyncio, asyncio, msgpack, logging, sys
from PyQt6.QtCore import QThread, pyqtSignal
from .message_protocol import Frame, MsgType

log = logging.getLogger(__name__)


class ZmqBridge(QThread):
    """
    Runs an asyncio SelectorEventLoop on a dedicated QThread.
    Bridges ZMQ I/O <-> Qt signals — UI main thread is never blocked.
    """
    token_received = pyqtSignal(str, str)   # session_id, token
    done_received  = pyqtSignal(str)         # session_id
    tool_call_gate = pyqtSignal(str, dict)   # session_id, tool_payload
    error_received = pyqtSignal(str, str)    # session_id, message

    ROUTER_ADDR = "tcp://127.0.0.1:5555"

    def __init__(self):
        super().__init__()
        self._loop:       asyncio.AbstractEventLoop | None = None
        self._socket:     zmq.asyncio.Socket | None = None
        self._send_queue: asyncio.Queue | None = None
        self._running     = True
        self._tasks:      list[asyncio.Task] = []

    # ── QThread.run ──────────────────────────────────────────────────────────
    def run(self):
        # Windows: ProactorEventLoop doesn't support ZMQ add_reader
        # Use SelectorEventLoop directly — no deprecated policy API needed
        self._loop = asyncio.SelectorEventLoop() if sys.platform == "win32" \
                     else asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._send_queue = asyncio.Queue()
        try:
            self._loop.run_until_complete(self._io_loop())
        except Exception as e:
            log.error(f"ZmqBridge loop error: {e}")
        finally:
            # Clean up all pending tasks before closing
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            self._loop.close()

    # ── Internal asyncio coroutines ──────────────────────────────────────────
    async def _io_loop(self):
        ctx = zmq.asyncio.Context()
        self._socket = ctx.socket(zmq.DEALER)
        self._socket.connect(self.ROUTER_ADDR)
        log.info(f"ZMQ bridge connected to {self.ROUTER_ADDR}")

        recv_task = asyncio.create_task(self._recv_loop(), name="zmq_recv")
        send_task = asyncio.create_task(self._send_loop(), name="zmq_send")
        self._tasks = [recv_task, send_task]

        try:
            await asyncio.gather(recv_task, send_task)
        except asyncio.CancelledError:
            pass
        finally:
            recv_task.cancel()
            send_task.cancel()
            await asyncio.gather(recv_task, send_task, return_exceptions=True)
            self._socket.close()
            ctx.term()

    async def _recv_loop(self):
        while self._running:
            try:
                raw = await self._socket.recv()
                frame = Frame.model_validate(msgpack.unpackb(raw, raw=False))
                self._dispatch(frame)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    log.warning(f"Bad frame: {e}")

    async def _send_loop(self):
        while self._running:
            try:
                frame: Frame = await asyncio.wait_for(
                    self._send_queue.get(), timeout=0.5
                )
                await self._socket.send(msgpack.packb(frame.model_dump()))
            except asyncio.TimeoutError:
                continue   # check _running flag again
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    log.warning(f"Send error: {e}")

    # ── Signal dispatch (called from asyncio thread — emits to Qt) ───────────
    def _dispatch(self, frame: Frame):
        match frame.type:
            case MsgType.CHAT_TOKEN:
                self.token_received.emit(frame.session_id, frame.payload.get("token", ""))
            case MsgType.CHAT_DONE:
                self.done_received.emit(frame.session_id)
            case MsgType.TOOL_CALL:
                self.tool_call_gate.emit(frame.session_id, frame.payload)
            case MsgType.ERROR:
                self.error_received.emit(frame.session_id, frame.payload.get("msg", "Unknown error"))

    # ── Public API (call from Qt main thread) ────────────────────────────────
    def send(self, frame: Frame):
        """Thread-safe enqueue — safe to call from any Qt thread."""
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._send_queue.put_nowait, frame)

    def stop(self):
        """Graceful shutdown: set flag, cancel tasks, stop loop."""
        self._running = False
        if self._loop and not self._loop.is_closed():
            # Cancel all running tasks from the Qt thread
            for task in self._tasks:
                self._loop.call_soon_threadsafe(task.cancel)
            self._loop.call_soon_threadsafe(self._loop.stop)

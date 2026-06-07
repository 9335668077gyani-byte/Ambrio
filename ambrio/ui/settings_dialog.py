# ambrio/ui/settings_dialog.py
"""
API Settings Dialog — lets the user add/remove/test API keys for each provider.
Keys are saved to the .env file in the project root.
Design: Dark OLED + Gold accent (#CA8A04) — matching Ambrio neumorphic theme.
"""
import os, asyncio, threading
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QScrollArea, QFrame,
    QSizePolicy, QMessageBox, QComboBox, QGroupBox,
)
from PyQt6.QtCore  import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui   import QFont, QColor, QPalette

ENV_PATH = Path(__file__).parents[2] / ".env"

# ── Colours ───────────────────────────────────────────────────────────────────
BG          = "#0C0A09"
SURFACE     = "#1C1917"
SURFACE2    = "#292524"
BORDER      = "#3D3836"
GOLD        = "#CA8A04"
GOLD_HOVER  = "#D97706"
TEXT        = "#F5F5F4"
TEXT_MUTED  = "#A8A29E"
SUCCESS     = "#22C55E"
ERROR_CLR   = "#EF4444"
WARNING     = "#F59E0B"

STYLE = f"""
QDialog {{
    background: {BG};
    color: {TEXT};
    font-family: 'Inter', 'Segoe UI', sans-serif;
}}
QTabWidget::pane {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QTabBar::tab {{
    background: {SURFACE};
    color: {TEXT_MUTED};
    padding: 10px 20px;
    font-size: 13px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    color: {GOLD};
    border-bottom: 2px solid {GOLD};
    background: {SURFACE2};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
    background: {SURFACE2};
}}
QGroupBox {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px;
    color: {TEXT};
    font-size: 13px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {GOLD};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
QLineEdit {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    color: {TEXT};
    font-size: 13px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
}}
QLineEdit:focus {{
    border: 1px solid {GOLD};
}}
QLineEdit::placeholder {{
    color: {TEXT_MUTED};
}}
QPushButton {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 16px;
    color: {TEXT};
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {BORDER};
    border-color: {GOLD};
    color: {GOLD};
}}
QPushButton#primary {{
    background: {GOLD};
    border: none;
    color: #000;
    font-weight: 700;
}}
QPushButton#primary:hover {{
    background: {GOLD_HOVER};
}}
QPushButton#danger {{
    border-color: {ERROR_CLR};
    color: {ERROR_CLR};
}}
QPushButton#danger:hover {{
    background: {ERROR_CLR}22;
}}
QPushButton#test_btn {{
    background: transparent;
    border: 1px solid {GOLD};
    color: {GOLD};
    padding: 6px 12px;
    font-size: 11px;
    border-radius: 5px;
}}
QPushButton#test_btn:hover {{
    background: {GOLD}22;
}}
QLabel {{
    color: {TEXT};
    font-size: 13px;
}}
QLabel#muted {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QLabel#section_title {{
    color: {GOLD};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: {SURFACE};
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {GOLD};
}}
QComboBox {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    color: {TEXT};
    font-size: 13px;
}}
QComboBox:focus {{
    border-color: {GOLD};
}}
QComboBox QAbstractItemView {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    color: {TEXT};
    selection-background-color: {GOLD}44;
}}
"""

# ── Provider definitions ──────────────────────────────────────────────────────
PROVIDERS = [
    {
        "id":      "groq",
        "name":    "Groq",
        "env":     "GROQ_API_KEYS",
        "models":  ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "deepseek-r1-distill-llama-70b", "gemma2-9b-it"],
        "url":     "https://console.groq.com",
        "tip":     "Fastest inference. Llama 3.3 70B is excellent for general tasks.",
        "free":    True,
    },
    {
        "id":      "gemini",
        "name":    "Google Gemini",
        "env":     "GEMINI_API_KEYS",
        "models":  ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"],
        "url":     "https://aistudio.google.com/apikey",
        "tip":     "Best for complex analysis. Gemini 2.5 Flash = 1M tokens/day free.",
        "free":    True,
    },
    {
        "id":      "openrouter",
        "name":    "OpenRouter",
        "env":     "OPENROUTER_API_KEYS",
        "models":  ["deepseek/deepseek-r1:free", "meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen3-235b-a22b:free"],
        "url":     "https://openrouter.ai",
        "tip":     "50+ free models including DeepSeek R1 (best reasoning model).",
        "free":    True,
    },
    {
        "id":      "cohere",
        "name":    "Cohere",
        "env":     "COHERE_API_KEYS",
        "models":  ["command-r-plus", "command-r"],
        "url":     "https://dashboard.cohere.com",
        "tip":     "Free trial. Good for RAG and document tasks.",
        "free":    True,
    },
    {
        "id":      "mistral",
        "name":    "Mistral AI",
        "env":     "MISTRAL_API_KEYS",
        "models":  ["mistral-small-latest", "mistral-medium-latest"],
        "url":     "https://console.mistral.ai",
        "tip":     "European provider. Free tier available.",
        "free":    True,
    },
    {
        "id":      "together",
        "name":    "Together AI",
        "env":     "TOGETHER_API_KEYS",
        "models":  ["meta-llama/Llama-3-70b-chat-hf", "mistralai/Mixtral-8x7B-Instruct-v0.1"],
        "url":     "https://api.together.xyz",
        "tip":     "Free $1 credits on signup. Many open models.",
        "free":    True,
    },
    {
        "id":      "xai",
        "name":    "xAI / Grok",
        "env":     "XAI_API_KEYS",
        "models":  ["grok-3-mini", "grok-3", "grok-2-1212"],
        "url":     "https://console.x.ai",
        "tip":     "Grok 3 Mini is free tier. Get your key at console.x.ai — starts with 'xai-'.",
        "free":    True,
    },
]

ROUTING_TASKS = [
    ("simple",    "Simple chat (quick questions)"),
    ("chat",      "General chat (main model)"),
    ("complex",   "Complex analysis & reports"),
    ("code",      "Code generation"),
    ("reasoning", "Math & logic (step-by-step)"),
    ("vision",    "Image understanding"),
    ("fast",      "Ultra-fast responses"),
]


# ── Test worker ───────────────────────────────────────────────────────────────
class ApiTestWorker(QThread):
    result = pyqtSignal(str, bool, str)  # provider, success, message

    def __init__(self, provider_id: str, api_key: str):
        super().__init__()
        self._provider = provider_id
        self._key      = api_key

    def run(self):
        import urllib.request, urllib.error, json

        # Strip ALL whitespace/invisible chars — common paste problem
        key = self._key.strip().replace("\n", "").replace("\r", "").replace(" ", "")

        # Cloudflare blocks Python's default urllib agent (error 1010) — use real browser UA
        UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

        try:
            if self._provider == "groq":
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {key}", "User-Agent": UA}
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                    count = len(data.get("data", []))
                    self.result.emit(self._provider, True, f"Valid key — {count} models available")

            elif self._provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                    count = len(data.get("models", []))
                    self.result.emit(self._provider, True, f"Valid key — {count} models available")

            elif self._provider == "openrouter":
                req = urllib.request.Request(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {key}", "User-Agent": UA}
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                    free = [m for m in data.get("data", []) if ":free" in m.get("id", "")]
                    self.result.emit(self._provider, True, f"Valid key — {len(free)} free models")

            elif self._provider == "xai":
                req = urllib.request.Request(
                    "https://api.x.ai/v1/models",
                    headers={"Authorization": f"Bearer {key}", "User-Agent": UA}
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read())
                    count = len(data.get("data", []))
                    self.result.emit(self._provider, True, f"Valid key — {count} Grok models")

            else:
                self.result.emit(self._provider, True, "Key saved (live test not available)")

        except urllib.error.HTTPError as e:
            # Read real error body from the API
            try:
                body = json.loads(e.read().decode())
                api_msg = (
                    body.get("error", {}).get("message")
                    or body.get("message")
                    or str(e)
                )
            except Exception:
                api_msg = str(e)

            if e.code == 403 and self._provider == "groq":
                self.result.emit(self._provider, False,
                    "HTTP 403 — Your Groq account needs PHONE VERIFICATION.\n"
                    "Go to console.groq.com → click your avatar → Verify Phone Number. "
                    "Then the key will work.")
            elif e.code == 401:
                self.result.emit(self._provider, False,
                    f"HTTP 401 — Key rejected. Check you copied the full key. Detail: {api_msg[:100]}")
            elif e.code == 403:
                self.result.emit(self._provider, False,
                    f"HTTP 403 — Account not activated or region blocked. Detail: {api_msg[:100]}")
            else:
                self.result.emit(self._provider, False,
                    f"API error {e.code}: {api_msg[:120]}")
        except Exception as e:
            msg = str(e)
            if "timeout" in msg.lower():
                self.result.emit(self._provider, False, "Request timed out — check internet")
            else:
                self.result.emit(self._provider, False, f"Error: {msg[:100]}")


# ── Key row widget ─────────────────────────────────────────────────────────────
class KeyRow(QWidget):
    removed = pyqtSignal(object)  # self

    def __init__(self, key: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Paste API key here…")
        self._input.setText(key)
        self._input.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self._input, stretch=1)

        toggle = QPushButton("👁")
        toggle.setFixedSize(34, 34)
        toggle.setToolTip("Show/hide key")
        toggle.clicked.connect(self._toggle_visibility)
        lay.addWidget(toggle)

        remove = QPushButton("✕")
        remove.setObjectName("danger")
        remove.setFixedSize(34, 34)
        remove.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(remove)

        self._visible = False

    def _toggle_visibility(self):
        self._visible = not self._visible
        mode = QLineEdit.EchoMode.Normal if self._visible else QLineEdit.EchoMode.Password
        self._input.setEchoMode(mode)

    def key(self) -> str:
        return self._input.text().strip()


# ── Provider tab ──────────────────────────────────────────────────────────────
class ProviderTab(QWidget):
    def __init__(self, provider: dict, current_keys: list[str]):
        super().__init__()
        self._provider = provider
        self._workers: list[ApiTestWorker] = []
        self._key_rows: list[KeyRow] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        # Header
        header = QHBoxLayout()
        name_lbl = QLabel(provider["name"])
        name_lbl.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {TEXT};")
        header.addWidget(name_lbl)

        badge = QLabel("FREE" if provider["free"] else "PAID")
        badge.setStyleSheet(
            f"background: {SUCCESS if provider['free'] else WARNING}22;"
            f"color: {SUCCESS if provider['free'] else WARNING};"
            f"border: 1px solid {SUCCESS if provider['free'] else WARNING}44;"
            f"border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: 700;"
        )
        header.addWidget(badge)
        header.addStretch()

        get_key_btn = QPushButton("Get Free API Key →")
        get_key_btn.setObjectName("test_btn")
        get_key_btn.clicked.connect(
            lambda: __import__("webbrowser").open(provider["url"])
        )
        header.addWidget(get_key_btn)
        lay.addLayout(header)

        # Tip
        tip = QLabel(f"ℹ  {provider['tip']}")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {BORDER};")
        lay.addWidget(line)

        # Keys section
        keys_group = QGroupBox("API KEYS (add multiple for auto-rotation)")
        keys_lay = QVBoxLayout(keys_group)
        keys_lay.setSpacing(8)

        self._keys_container = QVBoxLayout()
        self._keys_container.setSpacing(6)
        keys_lay.addLayout(self._keys_container)

        # Populate existing keys
        for k in (current_keys or [""]):
            self._add_key_row(k)

        # Add key button
        add_btn = QPushButton("+ Add Another Key")
        add_btn.clicked.connect(lambda: self._add_key_row(""))
        keys_lay.addWidget(add_btn)

        lay.addWidget(keys_group)

        # Test section
        test_group = QGroupBox("TEST CONNECTION")
        test_lay   = QHBoxLayout(test_group)
        test_lay.setSpacing(10)

        self._test_key_input = QLineEdit()
        self._test_key_input.setPlaceholderText("Paste a key to test it…")
        test_lay.addWidget(self._test_key_input, stretch=1)

        test_btn = QPushButton("Test Key")
        test_btn.setObjectName("test_btn")
        test_btn.clicked.connect(self._run_test)
        test_lay.addWidget(test_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        test_lay.addWidget(self._status_lbl)
        lay.addWidget(test_group)

        # Available models info
        models_group = QGroupBox("AVAILABLE MODELS")
        models_lay   = QVBoxLayout(models_group)
        for model in provider["models"]:
            m_lbl = QLabel(f"  •  {model}")
            m_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-family: 'Consolas', monospace; font-size: 12px;")
            models_lay.addWidget(m_lbl)
        lay.addWidget(models_group)

        lay.addStretch()

    def _add_key_row(self, key: str = ""):
        row = KeyRow(key)
        row.removed.connect(self._remove_key_row)
        self._keys_container.addWidget(row)
        self._key_rows.append(row)

    def _remove_key_row(self, row: KeyRow):
        if len(self._key_rows) <= 1:
            row._input.clear()
            return
        self._key_rows.remove(row)
        self._keys_container.removeWidget(row)
        row.deleteLater()

    def _run_test(self):
        key = self._test_key_input.text().strip()
        if not key:
            # Try first saved key
            keys = self.get_keys()
            if not keys:
                self._set_status("Paste a key first", False)
                return
            key = keys[0]

        if len(key) < 20:
            self._set_status("Key looks too short — check paste", False)
            return

        self._set_status("Testing… (may take a few seconds)", None)
        w = ApiTestWorker(self._provider["id"], key)
        w.result.connect(self._on_test_result)
        self._workers.append(w)
        w.start()

    def _on_test_result(self, provider: str, ok: bool, msg: str):
        self._set_status(msg, ok)

    def _set_status(self, msg: str, ok):
        if ok is None:
            color = WARNING
        elif ok:
            color = SUCCESS
        else:
            color = ERROR_CLR
        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(f"color: {color}; font-size: 12px;")

    def get_keys(self) -> list[str]:
        return [r.key() for r in self._key_rows if r.key()]


# ── Model Routing Tab ─────────────────────────────────────────────────────────
class RoutingTab(QWidget):
    def __init__(self, current_routing: dict[str, str]):
        super().__init__()
        from ambrio.router.model_registry import REGISTRY, list_models

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        title = QLabel("Model Routing — which model handles each task type")
        title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {TEXT};")
        lay.addWidget(title)

        desc = QLabel(
            "Ambrio auto-detects task type and routes to the best model. "
            "Override defaults here. Changes apply on next router restart."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        # Build all model aliases
        all_aliases = list(REGISTRY.keys())

        self._combos: dict[str, QComboBox] = {}

        for task_id, task_label in ROUTING_TASKS:
            row = QHBoxLayout()
            lbl = QLabel(task_label)
            lbl.setFixedWidth(240)
            row.addWidget(lbl)

            combo = QComboBox()
            for alias in all_aliases:
                from ambrio.router.model_registry import get_model
                m = get_model(alias)
                combo.addItem(f"{alias}  [{m.provider}]", alias)

            # Set current
            cur = current_routing.get(task_id, "")
            idx = next(
                (i for i in range(combo.count()) if combo.itemData(i) == cur), 0
            )
            combo.setCurrentIndex(idx)

            row.addWidget(combo, stretch=1)
            self._combos[task_id] = combo
            lay.addLayout(row)

        lay.addStretch()

    def get_routing(self) -> dict[str, str]:
        return {task: combo.currentData() for task, combo in self._combos.items()}


# ── Main Settings Dialog ──────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    """
    Main API Settings window.
    Opens via sidebar Settings button or keyboard shortcut.
    """
    keys_saved = pyqtSignal()  # emitted after successful save

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ambrio — API Settings")
        self.resize(780, 640)
        self.setStyleSheet(STYLE)

        self._env = self._load_env()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setStyleSheet(f"background: {SURFACE}; border-bottom: 1px solid {BORDER};")
        title_bar.setFixedHeight(56)
        tbl = QHBoxLayout(title_bar)
        tbl.setContentsMargins(20, 0, 20, 0)

        icon = QLabel("⚡")
        icon.setStyleSheet("font-size: 20px;")
        tbl.addWidget(icon)

        t = QLabel("API Settings")
        t.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {TEXT};")
        tbl.addWidget(t)
        tbl.addStretch()

        sub = QLabel("Keys are stored locally in .env — never sent anywhere")
        sub.setObjectName("muted")
        tbl.addWidget(sub)
        lay.addWidget(title_bar)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._provider_tabs: dict[str, ProviderTab] = {}
        for p in PROVIDERS:
            keys = self._env.get(p["env"], "").split(",")
            keys = [k.strip() for k in keys if k.strip()]
            tab  = ProviderTab(p, keys)
            self._provider_tabs[p["id"]] = tab
            self._tabs.addTab(tab, p["name"])

        # Routing tab
        from ambrio.router.model_registry import DEFAULT_ROUTING
        self._routing_tab = RoutingTab(DEFAULT_ROUTING)
        self._tabs.addTab(self._routing_tab, "Model Routing")

        lay.addWidget(self._tabs, stretch=1)

        # Footer buttons
        footer = QWidget()
        footer.setStyleSheet(f"background: {SURFACE}; border-top: 1px solid {BORDER};")
        footer.setFixedHeight(60)
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 0, 20, 0)

        self._status = QLabel("")
        self._status.setObjectName("muted")
        fl.addWidget(self._status)
        fl.addStretch()

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        fl.addWidget(cancel)

        save = QPushButton("Save & Restart Router")
        save.setObjectName("primary")
        save.setFixedWidth(180)
        save.clicked.connect(self._save)
        fl.addWidget(save)

        lay.addWidget(footer)

    # ── .env I/O ──────────────────────────────────────────────────────────────
    def _load_env(self) -> dict[str, str]:
        """Parse .env into a dict."""
        env: dict[str, str] = {}
        if not ENV_PATH.exists():
            return env
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
        return env

    def _save_env(self, env: dict[str, str]):
        """Write env dict back to .env, preserving comments."""
        lines: list[str] = []

        # Keep existing comment lines from the template
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    lines.append(line)

        lines.append("")
        lines.append("# ── API Keys (auto-written by Ambrio Settings) ──────────────")
        for k, v in env.items():
            lines.append(f"{k}={v}")

        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _save(self):
        """Collect keys from all tabs, write .env, signal restart."""
        env = {}

        # Collect provider keys
        for p in PROVIDERS:
            tab  = self._provider_tabs[p["id"]]
            keys = tab.get_keys()
            env[p["env"]] = ",".join(keys)

        # Collect routing overrides
        routing = self._routing_tab.get_routing()
        env["AMBRIO_MODEL_SIMPLE"]    = routing.get("simple",    "")
        env["AMBRIO_MODEL_CHAT"]      = routing.get("chat",      "")
        env["AMBRIO_MODEL_COMPLEX"]   = routing.get("complex",   "")
        env["AMBRIO_MODEL_CODE"]      = routing.get("code",      "")
        env["AMBRIO_MODEL_REASONING"] = routing.get("reasoning", "")
        env["AMBRIO_MODEL_VISION"]    = routing.get("vision",    "")
        env["AMBRIO_MODEL_FAST"]      = routing.get("fast",      "")

        try:
            self._save_env(env)
            self._status.setText("✓  Saved to .env")
            self._status.setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
            self.keys_saved.emit()

            QTimer.singleShot(1500, self.accept)
        except Exception as e:
            self._status.setText(f"Save failed: {e}")
            self._status.setStyleSheet(f"color: {ERROR_CLR}; font-size: 12px;")

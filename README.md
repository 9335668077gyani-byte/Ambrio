# 🧠 Ambrio — Personal Autonomous AI Assistant

> Runs **100% locally**. No cloud. No API keys. Powered by [Ollama](https://ollama.com).

---

## 🚀 Quick Start

```powershell
# First time setup + launch
.\start_ambrio.ps1
```

Or if already set up:
```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

---

## ⚙️ Requirements

| Requirement | Details |
|---|---|
| Python | 3.10 or higher |
| [Ollama](https://ollama.com/download) | Installed and running |
| Model | `codegemma` (auto-pulled on first run) |

---

## 📁 Project Structure

```
Ambrio/
├── app.py              ← Main Streamlit app
├── requirements.txt    ← Python dependencies
├── start_ambrio.ps1    ← One-click setup + launch
└── README.md
```

---

## 🛠️ Powered By

- [Streamlit](https://streamlit.io) — UI framework
- [Ollama](https://ollama.com) — Local LLM runner
- [CodeGemma](https://ollama.com/library/codegemma) — AI model

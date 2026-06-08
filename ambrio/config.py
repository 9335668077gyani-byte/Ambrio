# ambrio/config.py
"""
Loads all API keys from environment / .env file.
Each provider supports multiple comma-separated keys for rotation.

Example .env:
  GROQ_API_KEYS=gsk_key1,gsk_key2,gsk_key3
  GEMINI_API_KEYS=AIzaSy_key1,AIzaSy_key2

Override routing defaults (optional):
  AMBRIO_MODEL_SIMPLE    = os.getenv("AMBRIO_MODEL_SIMPLE",    "openrouter/llama-3.3-70b")
  AMBRIO_MODEL_CHAT      = os.getenv("AMBRIO_MODEL_CHAT",      "openrouter/llama-3.3-70b")
  AMBRIO_MODEL_COMPLEX   = os.getenv("AMBRIO_MODEL_COMPLEX",   "openrouter/llama-3.3-70b")
  AMBRIO_MODEL_CODE      = os.getenv("AMBRIO_MODEL_CODE",      "openrouter/deepseek-v3")
  AMBRIO_MODEL_REASONING = os.getenv("AMBRIO_MODEL_REASONING", "openrouter/deepseek-v3")
  AMBRIO_MODEL_VISION    = os.getenv("AMBRIO_MODEL_VISION",    "gemini/2.5-flash")
  AMBRIO_MODEL_FAST      = os.getenv("AMBRIO_MODEL_FAST",      "openrouter/llama-3.1-8b")
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[1] / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed yet — keys from env only


def _keys(env_var: str) -> list[str]:
    raw = os.environ.get(env_var, "").strip()
    return [k.strip() for k in raw.split(",") if k.strip()]


PROVIDER_KEYS: dict[str, list[str]] = {
    "groq":       _keys("GROQ_API_KEYS"),
    "gemini":     _keys("GEMINI_API_KEYS"),
    "cohere":     _keys("COHERE_API_KEYS"),
    "mistral":    _keys("MISTRAL_API_KEYS"),
    "openrouter": _keys("OPENROUTER_API_KEYS"),
    "together":   _keys("TOGETHER_API_KEYS"),
    "cerebras":   _keys("CEREBRAS_API_KEYS"),
    "xai":        _keys("XAI_API_KEYS"),        # Grok (xAI) — get key at console.x.ai
}

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

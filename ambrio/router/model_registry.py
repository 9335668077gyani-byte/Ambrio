# ambrio/router/model_registry.py
"""
Central model registry for Ambrio's multi-model router.

HOW TO ADD A NEW MODEL:
  1. Add an entry to REGISTRY below.
  2. If it's a new provider, add its base_url to PROVIDER_BASE_URLS.
  3. Add its API key env var to .env.example and config.py.
  That's it. No other code changes needed.

REGISTRY FORMAT:
  "<model_alias>": ModelDef(
      provider   = "<provider_name>",   # must match a key in PROVIDER_BASE_URLS
      model_id   = "<exact API model string>",
      context_k  = <context window in K tokens>,
      tier       = "free" | "paid",
      strengths  = ["chat", "code", "vision", "reasoning", "fast"],
      notes      = "optional human-readable note",
  )
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelDef:
    provider:   str
    model_id:   str
    context_k:  int                    # context window in K tokens
    tier:       str = "free"           # "free" | "paid"
    strengths:  list[str] = field(default_factory=list)
    notes:      str = ""

    def __post_init__(self):
        object.__setattr__(self, "strengths", list(self.strengths))


# ── Provider base URLs (OpenAI-compatible) ────────────────────────────────────
PROVIDER_BASE_URLS: dict[str, str] = {
    "groq":       "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "cohere":     "https://api.cohere.ai/compatibility/v1",
    "mistral":    "https://api.mistral.ai/v1",
    "together":   "https://api.together.xyz/v1",
    "cerebras":   "https://api.cerebras.ai/v1",
    "xai":        "https://api.x.ai/v1",           # Grok models by xAI
    "ollama":     "http://localhost:11434/v1",   # Ollama OpenAI-compat endpoint
    # Gemini uses its own SSE endpoint — handled separately in the adapter
    "gemini":     "https://generativelanguage.googleapis.com/v1beta",
}

# ── Model Registry ────────────────────────────────────────────────────────────
# Last verified: June 2025
# To add a new model: copy any entry below and change the values.
REGISTRY: dict[str, ModelDef] = {

    # ── Groq (fastest inference, free tier) ───────────────────────────────────
    "groq/llama-3.3-70b": ModelDef(
        provider  = "groq",
        model_id  = "llama-3.3-70b-versatile",
        context_k = 128,
        tier      = "free",
        strengths = ["chat", "reasoning", "code"],
        notes     = "Best Groq free model as of June 2025",
    ),
    "groq/llama-3.1-8b": ModelDef(
        provider  = "groq",
        model_id  = "llama-3.1-8b-instant",
        context_k = 128,
        tier      = "free",
        strengths = ["fast", "chat"],
        notes     = "Ultra-fast, lightweight",
    ),
    "groq/gemma2-9b": ModelDef(
        provider  = "groq",
        model_id  = "gemma2-9b-it",
        context_k = 8,
        tier      = "free",
        strengths = ["chat", "fast"],
    ),
    "groq/deepseek-r1-70b": ModelDef(
        provider  = "groq",
        model_id  = "deepseek-r1-distill-llama-70b",
        context_k = 128,
        tier      = "free",
        strengths = ["reasoning", "math"],
        notes     = "Best free reasoning model on Groq",
    ),

    # ── Gemini (Google, free tier via AI Studio key) ──────────────────────────
    "gemini/2.5-flash": ModelDef(
        provider  = "gemini",
        model_id  = "gemini-2.5-flash",
        context_k = 1000,
        tier      = "free",
        strengths = ["chat", "reasoning", "vision", "code"],
        notes     = "Current best free Gemini model (June 2025)",
    ),
    "gemini/2.5-flash-lite": ModelDef(
        provider  = "gemini",
        model_id  = "gemini-2.5-flash-lite",
        context_k = 1000,
        tier      = "free",
        strengths = ["fast", "chat"],
        notes     = "Fastest Gemini, very low latency",
    ),
    "gemini/2.0-flash": ModelDef(
        provider  = "gemini",
        model_id  = "gemini-2.0-flash",
        context_k = 1000,
        tier      = "free",
        strengths = ["chat", "vision", "fast"],
        notes     = "Fallback if 2.5 not available",
    ),

    # ── OpenRouter (50+ free models, rate-limited) ────────────────────────────
    "openrouter/llama-3.3-70b": ModelDef(
        provider  = "openrouter",
        model_id  = "meta-llama/llama-3.3-70b-instruct:free",
        context_k = 131,
        tier      = "free",
        strengths = ["chat", "reasoning"],
    ),
    "openrouter/deepseek-r1": ModelDef(
        provider  = "openrouter",
        model_id  = "deepseek/deepseek-r1:free",
        context_k = 163,
        tier      = "free",
        strengths = ["reasoning", "math", "code"],
        notes     = "Best free reasoning model overall",
    ),
    "openrouter/deepseek-v3": ModelDef(
        provider  = "openrouter",
        model_id  = "deepseek/deepseek-chat-v3-0324:free",
        context_k = 163,
        tier      = "free",
        strengths = ["chat", "code"],
    ),
    "openrouter/gemma-3-27b": ModelDef(
        provider  = "openrouter",
        model_id  = "google/gemma-3-27b-it:free",
        context_k = 8,
        tier      = "free",
        strengths = ["chat"],
    ),
    "openrouter/qwen3-235b": ModelDef(
        provider  = "openrouter",
        model_id  = "qwen/qwen3-235b-a22b:free",
        context_k = 40,
        tier      = "free",
        strengths = ["reasoning", "math", "code"],
        notes     = "Massive MoE, excellent reasoning",
    ),

    # ── Cohere (free trial) ───────────────────────────────────────────────────
    "cohere/command-r-plus": ModelDef(
        provider  = "cohere",
        model_id  = "command-r-plus",
        context_k = 128,
        tier      = "free",
        strengths = ["chat", "reasoning"],
    ),

    # ── Mistral (free tier) ───────────────────────────────────────────────────
    "mistral/small": ModelDef(
        provider  = "mistral",
        model_id  = "mistral-small-latest",
        context_k = 32,
        tier      = "free",
        strengths = ["chat", "code"],
    ),

    # ── Local Ollama (always free, private) ───────────────────────────────────
    "ollama/phi3-mini": ModelDef(
        provider  = "ollama",
        model_id  = "phi3:mini",
        context_k = 128,
        tier      = "free",
        strengths = ["chat", "fast"],
        notes     = "Microsoft Phi-3 Mini 3.8B — follows instructions, no refusals",
    ),
    "ollama/llama3.2-1b": ModelDef(
        provider  = "ollama",
        model_id  = "llama3.2:1b",
        context_k = 128,
        tier      = "free",
        strengths = ["fast"],
        notes     = "Tiny fallback only — poor instruction following",
    ),
    "ollama/llama3.2-3b": ModelDef(
        provider  = "ollama",
        model_id  = "llama3.2:3b",
        context_k = 128,
        tier      = "free",
        strengths = ["chat"],
    ),
    "ollama/codellama": ModelDef(
        provider  = "ollama",
        model_id  = "codellama:7b",
        context_k = 16,
        tier      = "free",
        strengths = ["code"],
    ),
    "ollama/deepseek-r1": ModelDef(
        provider  = "ollama",
        model_id  = "deepseek-r1:7b",
        context_k = 128,
        tier      = "free",
        strengths = ["reasoning"],
    ),

    # ── xAI / Grok ────────────────────────────────────────────────────────────────
    "xai/grok-3-mini": ModelDef(
        provider  = "xai",
        model_id  = "grok-3-mini",
        context_k = 131,
        tier      = "free",
        strengths = ["reasoning", "chat", "fast"],
        notes     = "Grok 3 Mini — fast reasoning, free tier (May 2025)",
    ),
    "xai/grok-3": ModelDef(
        provider  = "xai",
        model_id  = "grok-3",
        context_k = 131,
        tier      = "paid",
        strengths = ["chat", "reasoning", "code"],
        notes     = "Grok 3 — flagship xAI model",
    ),
    "xai/grok-2": ModelDef(
        provider  = "xai",
        model_id  = "grok-2-1212",
        context_k = 131,
        tier      = "paid",
        strengths = ["chat", "code"],
        notes     = "Grok 2 — stable production model",
    ),
}


# ── Routing Rules ─────────────────────────────────────────────────────────────
# Default model aliases per task type.
# Change these to swap models globally — or set overrides in .env.
# Format: "<task_type>": "<registry_alias>"
#
# To change the default: edit the alias here, OR set in .env:
#   AMBRIO_MODEL_CHAT=groq/deepseek-r1-70b
#   AMBRIO_MODEL_CODE=ollama/codellama
#   AMBRIO_MODEL_REASONING=openrouter/deepseek-r1

import os

DEFAULT_ROUTING: dict[str, str] = {
    "simple":    os.environ.get("AMBRIO_MODEL_SIMPLE",    "openrouter/llama-3.3-70b"),  # fast, obedient
    "chat":      os.environ.get("AMBRIO_MODEL_CHAT",      "openrouter/llama-3.3-70b"),  # best free chat
    "complex":   os.environ.get("AMBRIO_MODEL_COMPLEX",   "openrouter/llama-3.3-70b"),  # heavy tasks
    "code":      os.environ.get("AMBRIO_MODEL_CODE",      "openrouter/deepseek-v3"),    # coding
    "reasoning": os.environ.get("AMBRIO_MODEL_REASONING", "openrouter/deepseek-v3"),    # reasoning
    "cloud_reasoning": os.environ.get("AMBRIO_MODEL_CLOUD_REASONING", "groq/llama-3.3-70b"), # planner/critic pin
    "vision":    os.environ.get("AMBRIO_MODEL_VISION",    "gemini/2.5-flash"),           # vision/images — can actually see
    "fast":      os.environ.get("AMBRIO_MODEL_FAST",      "openrouter/llama-3.1-8b"),   # ultra fast
    # ── Task-specific routes ──────────────────────────────────────────────────
    # OCR/image/doc: the REAL work is done by Python tools (easyocr, Pillow, docx).
    # The LLM just needs to call the right tool — use the most obedient fast model.
    "ocr":       os.environ.get("AMBRIO_MODEL_OCR",       "openrouter/llama-3.3-70b"),  # calls img_ocr()
    "image":     os.environ.get("AMBRIO_MODEL_IMAGE",     "openrouter/llama-3.3-70b"),  # calls doc_convert/combine
    "doc":       os.environ.get("AMBRIO_MODEL_DOC",       "openrouter/llama-3.3-70b"),  # calls doc_read/save
}

# ── Fallback chain when primary model's keys are exhausted ───────────────────
# Tried in order until one succeeds. Ollama is always last resort.
FALLBACK_CHAIN: list[str] = [
    "groq/llama-3.3-70b",
    "gemini/2.5-flash",
    "openrouter/llama-3.3-70b",
    "openrouter/deepseek-v3",
    "cohere/command-r-plus",
    "mistral/small",
    "ollama/phi3-mini",      # best local fallback
    "ollama/llama3.2-1b",   # last resort
]


def get_model(alias: str) -> ModelDef | None:
    """Lookup a model by alias. Returns None if not found."""
    return REGISTRY.get(alias)


def list_models(provider: str | None = None, tier: str | None = None) -> list[str]:
    """List all model aliases, optionally filtered by provider or tier."""
    return [
        alias for alias, m in REGISTRY.items()
        if (provider is None or m.provider == provider)
        and (tier is None or m.tier == tier)
    ]


def print_registry():
    """Pretty-print all registered models. Useful for debugging."""
    print(f"\n{'ALIAS':<35} {'PROVIDER':<12} {'MODEL ID':<45} {'TIER':<6} STRENGTHS")
    print("-" * 120)
    for alias, m in REGISTRY.items():
        strengths = ", ".join(m.strengths)
        print(f"{alias:<35} {m.provider:<12} {m.model_id:<45} {m.tier:<6} {strengths}")


if __name__ == "__main__":
    print_registry()

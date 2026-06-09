# ambrio/router/model_router.py
"""
Multi-model router with free-tier API key rotation.

Uses model_registry.py as the single source of truth for model names.
Routing is complexity-aware: simple tasks stay local, complex tasks
use the best available API model with auto key-rotation on 429.
"""
import asyncio, time, logging, json
from typing import AsyncIterator
from .model_registry import (
    REGISTRY, PROVIDER_BASE_URLS, DEFAULT_ROUTING, FALLBACK_CHAIN,
    ModelDef, get_model, list_models
)

log = logging.getLogger(__name__)

# Complexity keywords — any of these in the user message = "complex" task
_COMPLEX_KW = [
    "analyze", "report", "summarize", "compare", "detailed", "research",
    "plan", "strategy", "write a", "explain why", "comprehensive", "entire",
    "multi-step", "all the", "step by step", "in depth",
]

# Task-type keyword maps — checked BEFORE complexity
_TASK_KW = {
    "ocr":    ["extract text", "read this", "read the", "what does it say",
               "what is written", "copy text", "ocr", "read image",
               "text from image", "get text", "scan text"],
    "image":  ["convert to pdf", "make pdf", "image to pdf", "combine",
               "doc_combine", "to pdf"],
    "doc":    ["edit this", "edit the doc", "modify", "rewrite", "translate",
               "format this", "save as", "make it docx", "make word"],
    "vision": ["describe", "what is in", "what's in this image", "look at",
               "see this", "identify"],
}


class KeyPool:
    """
    Round-robin key manager for a single provider.
    Auto-skips rate-limited keys; resets after reset_seconds.
    """
    def __init__(self, provider: str, keys: list[str], reset_seconds: int = 60):
        self.provider    = provider
        self._keys       = list(keys)
        self._idx        = 0
        self._limited: dict[str, float] = {}
        self._reset_secs = reset_seconds

    def next(self) -> str | None:
        """Return next available key, or None if all are rate-limited."""
        now, seen = time.monotonic(), 0
        while seen < len(self._keys):
            key = self._keys[self._idx % len(self._keys)]
            self._idx += 1
            seen += 1
            ts = self._limited.get(key)
            if ts is None or (now - ts) >= self._reset_secs:
                self._limited.pop(key, None)
                return key
        return None

    def peek(self) -> bool:
        """Returns True if at least one key is available (non-destructive)."""
        tmp_idx = self._idx
        result  = self.next() is not None
        self._idx = tmp_idx
        return result

    def mark_limited(self) -> None:
        """Mark the most-recently-returned key as rate-limited."""
        if not self._keys:
            return
        key = self._keys[(self._idx - 1) % len(self._keys)]
        self._limited[key] = time.monotonic()
        log.warning(f"[{self.provider}] key …{key[-4:]} rate-limited → rotating")

    @property
    def available_count(self) -> int:
        now = time.monotonic()
        return sum(
            1 for k in self._keys
            if k not in self._limited or (now - self._limited[k]) >= self._reset_secs
        )


class ModelRouter:
    """
    Routes chat requests to the best available model.

    Resolution order per request:
      1. Detect complexity (simple / complex / code / reasoning)
      2. Look up preferred model from DEFAULT_ROUTING
      3. If provider has no keys → walk FALLBACK_CHAIN
      4. Stream response; on 429 rotate key and retry
      5. Ultimate fallback: local Ollama (always available)

    To add a new model: edit model_registry.py only.
    """

    def __init__(self, provider_keys: dict[str, list[str]]):
        # Build key pools for each provider that has keys configured
        self._pools: dict[str, KeyPool] = {
            name: KeyPool(name, keys)
            for name, keys in provider_keys.items()
            if keys
        }
        self._log_available_providers()

    def _log_available_providers(self):
        available = list(self._pools.keys())
        log.info(f"ModelRouter initialized. API providers: {available or ['none — ollama-only mode']}")
        for provider, pool in self._pools.items():
            log.info(f"  {provider}: {pool.available_count} key(s)")

    # ── Complexity detection ──────────────────────────────────────────────────

    def _detect_complexity(self, text: str, has_image: bool = False) -> str:
        t = text.lower()

        # ── Task-specific detection (highest priority) ────────────────────────
        for task, keywords in _TASK_KW.items():
            if any(kw in t for kw in keywords):
                return task

        # If image attached with no clear intent → default to ocr
        if has_image and len(t.strip()) < 30:
            return "ocr"

        # ── Complexity detection ──────────────────────────────────────────────
        if any(kw in t for kw in ["```", "def ", "class ", "import ", "SELECT", "CREATE"]):
            return "code"
        if any(kw in t for kw in ["why", "reason", "logic", "prove", "solve", "calculate"]):
            return "reasoning"
        if len(t) > 150 or any(kw in t for kw in _COMPLEX_KW):
            return "complex"
        return "simple"

    def _select_model_alias(self, text: str, task_type: str | None = None,
                             has_image: bool = False) -> str:
        """
        Returns the best available model alias for this request.
        Falls through FALLBACK_CHAIN if the preferred provider has no keys.
        """
        if task_type is None:
            task_type = self._detect_complexity(text, has_image=has_image)

        log.info(f"ModelRouter task_type={task_type} has_image={has_image}")

        # Get preferred alias from routing table
        preferred = DEFAULT_ROUTING.get(task_type, DEFAULT_ROUTING["chat"])
        model     = get_model(preferred)

        if model and self._provider_available(model.provider):
            return preferred

        # Walk fallback chain
        for alias in FALLBACK_CHAIN:
            m = get_model(alias)
            if m and self._provider_available(m.provider):
                log.info(f"Fallback: {preferred} → {alias}")
                return alias

        # Ultimate fallback: local ollama
        return "ollama/llama3.2-1b"

    def _provider_available(self, provider: str) -> bool:
        if provider == "ollama":
            return True  # always available
        pool = self._pools.get(provider)
        return pool is not None and pool.peek()

    # ── Public streaming interface ────────────────────────────────────────────

    async def stream(
        self,
        messages:   list[dict],
        tools:      list | None = None,
        task_type:  str | None  = None,
    ) -> AsyncIterator[dict]:
        """
        Stream response in Ollama-compatible chunk format:
          {"message": {"content": "token"}, "done": False}
          {"done": True}
        """
        user_text  = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        # Detect if any [IMAGE FILE: ...] block is in the user message
        has_image  = '[IMAGE FILE:' in user_text or '[BINARY FILE:' in user_text
        alias = self._select_model_alias(user_text, task_type, has_image=has_image)
        model = get_model(alias)

        log.info(f"ModelRouter → {alias} ({model.model_id if model else '?'})")

        try:
            async for chunk in self._dispatch(alias, model, messages, tools):
                yield chunk
        except Exception as e:
            log.error(f"Model {alias} FAILED ({type(e).__name__}: {e}) — falling back to Ollama")
            async for chunk in self._stream_ollama(messages, tools):
                yield chunk

    async def _dispatch(self, alias: str, model: ModelDef, messages, tools):
        if model.provider == "ollama":
            async for c in self._stream_ollama(messages, tools):
                yield c
        elif model.provider == "gemini":
            async for c in self._stream_gemini(model, messages):
                yield c
        else:
            # All other providers use OpenAI-compatible streaming
            pool     = self._pools[model.provider]
            base_url = PROVIDER_BASE_URLS[model.provider]
            async for c in self._stream_openai_compat(model, pool, base_url, messages):
                yield c

    # ── Provider adapters ─────────────────────────────────────────────────────

    async def _stream_ollama(self, messages: list[dict], tools=None):
        """Delegate to existing OllamaClient."""
        from .ollama_client import OllamaClient
        async for chunk in OllamaClient().stream(messages, tools=tools):
            yield chunk

    async def _stream_openai_compat(
        self,
        model:    ModelDef,
        pool:     KeyPool,
        base_url: str,
        messages: list[dict],
        retries:  int = 3,
    ):
        """Stream from any OpenAI-compatible endpoint with key rotation on 429."""
        import aiohttp

        for attempt in range(retries):
            api_key = pool.next()
            if not api_key:
                log.warning(f"All {pool.provider} keys exhausted")
                return

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
                # Real browser UA prevents Cloudflare 403/1010 blocks
                "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            if pool.provider == "openrouter":
                headers["HTTP-Referer"] = "https://github.com/9335668077gyani-byte/Ambrio"
                headers["X-Title"]      = "Ambrio Local AI"

            body = {
                "model":    model.model_id,
                "messages": messages,
                "stream":   True,
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{base_url}/chat/completions",
                        headers=headers, json=body,
                        timeout=aiohttp.ClientTimeout(total=90)
                    ) as resp:
                        if resp.status == 429:
                            pool.mark_limited()
                            log.warning(f"{pool.provider} rate limited (attempt {attempt+1}/{retries})")
                            await asyncio.sleep(1.0 * (attempt + 1))
                            continue
                        if resp.status == 401:
                            log.error(f"{pool.provider} invalid API key ...{api_key[-4:]}")
                            pool.mark_limited()
                            continue
                        if resp.status == 403:
                            body_text = await resp.text()
                            log.error(f"{pool.provider} HTTP 403 — account/key issue: {body_text[:200]}")
                            pool.mark_limited()
                            continue
                        resp.raise_for_status()
                        async for line in resp.content:
                            decoded = line.decode(errors="ignore").strip()
                            if not decoded.startswith("data:"):
                                continue
                            data = decoded[5:].strip()
                            if data == "[DONE]":
                                yield {"done": True}
                                return
                            try:
                                obj   = json.loads(data)
                                delta = obj["choices"][0]["delta"]
                                token = delta.get("content", "")
                                if token:
                                    yield {"done": False, "message": {"content": token}}
                            except Exception:
                                pass
                        yield {"done": True}
                        return
            except Exception as e:
                log.error(f"{pool.provider} attempt {attempt+1} FAILED: {type(e).__name__}: {e}")
                if attempt == retries - 1:
                    raise

    async def _stream_gemini(self, model: ModelDef, messages: list[dict]):
        """Stream from Google Gemini SSE endpoint."""
        import aiohttp

        pool    = self._pools.get("gemini")
        api_key = pool.next() if pool else None
        if not api_key:
            raise RuntimeError("No Gemini API keys configured")

        # Convert messages — Gemini uses "user" / "model" roles only
        contents = [
            {
                "role":  "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in messages if m["role"] in ("user", "assistant")
        ]
        system_text = next(
            (m["content"] for m in messages if m["role"] == "system"), None
        )
        body = {"contents": contents}
        if system_text:
            body["system_instruction"] = {"parts": [{"text": system_text}]}

        url = (
            f"{PROVIDER_BASE_URLS['gemini']}/models/"
            f"{model.model_id}:streamGenerateContent"
            f"?key={api_key}&alt=sse"
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=body, timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status == 429:
                    pool.mark_limited()
                    raise RuntimeError("Gemini rate limited — rotating key")
                if resp.status == 400:
                    text = await resp.text()
                    raise RuntimeError(f"Gemini bad request: {text[:200]}")
                resp.raise_for_status()
                async for line in resp.content:
                    decoded = line.decode(errors="ignore").strip()
                    if not decoded.startswith("data:"):
                        continue
                    try:
                        obj = json.loads(decoded[5:])
                        token = (
                            obj["candidates"][0]["content"]["parts"][0]["text"]
                        )
                        if token:
                            yield {"done": False, "message": {"content": token}}
                    except Exception:
                        pass
        yield {"done": True}

    # ── Inspection helpers ────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return current router status — useful for a /status command in chat."""
        return {
            "providers": {
                name: {
                    "keys_available": pool.available_count,
                    "total_keys":     len(pool._keys),
                }
                for name, pool in self._pools.items()
            },
            "routing": DEFAULT_ROUTING,
            "total_models_registered": len(REGISTRY),
        }

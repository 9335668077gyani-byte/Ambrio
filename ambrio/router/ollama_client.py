# ambrio/router/ollama_client.py
import aiohttp, json, os, logging
from typing import AsyncGenerator

log = logging.getLogger(__name__)

# Model preference order — first match wins
MODEL_PREFERENCE = [
    "phi3:mini",      # best local — follows instructions, no refusals
    "phi3",
    "codegemma",
    "mistral",
    "llama3.2:3b",
    "llama3.2",
    "llama3",
    "gemma2",
    "llama3.2:1b",   # last resort — poor instruction following
]


class OllamaClient:
    BASE_URL  = "http://localhost:11434"
    TIMEOUT_S = 120

    def __init__(self, model: str | None = None):
        # Priority: env var > explicit arg > auto-detect on first use
        self.model = model or os.environ.get("AMBRIO_MODEL") or None
        self._resolved = self.model is not None

    async def _resolve_model(self) -> str:
        """Auto-detect best available model from running Ollama instance."""
        if self._resolved:
            return self.model
        try:
            available = await self.list_models()
            log.info(f"Available Ollama models: {available}")
            for preferred in MODEL_PREFERENCE:
                for avail in available:
                    if avail.startswith(preferred):
                        self.model = avail
                        self._resolved = True
                        log.info(f"Auto-selected model: {self.model}")
                        return self.model
            # Last resort: use whatever is installed
            if available:
                self.model = available[0]
                self._resolved = True
                log.warning(f"No preferred model found — using: {self.model}")
                return self.model
        except Exception as e:
            log.warning(f"Model auto-detect failed: {e}")
        # Hard fallback
        self.model = "llama3.2:1b"
        self._resolved = True
        return self.model

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        response_format: dict | None = None
    ) -> AsyncGenerator[dict, None]:
        model = await self._resolve_model()
        payload: dict = {
            "model":    model,
            "messages": messages,
            "stream":   True,
            "options":  {},
        }
        # Drop temperature to reduce hallucinations when strictly adhering to a JSON Schema
        payload["options"]["temperature"] = 0.1 if response_format else 0.7
        # Small / basic models don't support tool calling — skip to avoid errors
        supports_tools = not any(m in model for m in ["1b", "phi3", "gemma:"])
        if tools and supports_tools:
            payload["tools"] = tools
        if response_format:
            payload["format"] = response_format

        timeout = aiohttp.ClientTimeout(total=self.TIMEOUT_S)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{self.BASE_URL}/api/chat",
                json=payload
            ) as resp:
                resp.raise_for_status()
                async for raw_line in resp.content:
                    line = raw_line.strip()
                    if not line:
                        continue
                    yield json.loads(line)

    async def list_models(self) -> list[str]:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.BASE_URL}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                data = await resp.json()
        return [m["name"] for m in data.get("models", [])]

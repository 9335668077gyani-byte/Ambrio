# ambrio/router/ollama_client.py
import aiohttp, json
from typing import AsyncGenerator

class OllamaClient:
    BASE_URL  = "http://localhost:11434"
    MODEL     = "codegemma"
    TIMEOUT_S = 120

    def __init__(self, model: str = MODEL):
        self.model = model

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None
    ) -> AsyncGenerator[dict, None]:
        payload: dict = {
            "model":    self.model,
            "messages": messages,
            "stream":   True,
        }
        if tools:
            payload["tools"] = tools

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
            async with session.get(f"{self.BASE_URL}/api/tags") as resp:
                data = await resp.json()
        return [m["name"] for m in data.get("models", [])]

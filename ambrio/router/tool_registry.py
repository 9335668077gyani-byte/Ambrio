# ambrio/router/tool_registry.py
import functools, inspect
from typing import Callable, Any

_REGISTRY: dict[str, Callable] = {}

def tool(name: str | None = None):
    """Decorator to register an async function as an RPC-callable tool."""
    def decorator(fn: Callable) -> Callable:
        key = name or fn.__name__
        assert inspect.iscoroutinefunction(fn), f"Tool '{key}' must be async"
        _REGISTRY[key] = fn

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            return await fn(*args, **kwargs)
        return wrapper
    return decorator

class ToolRegistry:
    async def dispatch(self, tool_name: str, args: dict) -> Any:
        fn = _REGISTRY.get(tool_name)
        if not fn:
            raise KeyError(f"Unknown tool: {tool_name!r}")
        return await fn(**args)

    def schema(self) -> list[dict]:
        """Returns Ollama-compatible tool schema for all registered tools."""
        schemas = []
        for name, fn in _REGISTRY.items():
            sig = inspect.signature(fn)
            schemas.append({
                "type": "function",
                "function": {
                    "name":        name,
                    "description": (fn.__doc__ or "").strip(),
                    "parameters": {
                        "type":       "object",
                        "properties": {
                            p: {"type": "string"} for p in sig.parameters
                        },
                        "required": list(sig.parameters.keys())
                    }
                }
            })
        return schemas

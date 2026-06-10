# tests/unit/test_dispatch_tool.py
"""Unit tests for executor._dispatch_tool — the tool registry lookup logic."""
import pytest
from unittest.mock import AsyncMock, patch
from ambrio.agents.nodes.executor import _dispatch_tool, _TOOL_REGISTRY, register_tool


@pytest.fixture(autouse=True)
def clean_registry():
    """Isolate each test — save and restore registry state."""
    original = dict(_TOOL_REGISTRY)
    yield
    _TOOL_REGISTRY.clear()
    _TOOL_REGISTRY.update(original)


@pytest.mark.asyncio
async def test_dispatch_known_tool_calls_callable():
    mock_fn = AsyncMock(return_value={"data": 42})
    _TOOL_REGISTRY["test_tool"] = mock_fn
    result = await _dispatch_tool("test_tool", {"key": "val"})
    assert result == {"data": 42}
    mock_fn.assert_awaited_once_with({"key": "val"})


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_raises_key_error():
    with patch("ambrio.agents.nodes.executor._tools_loaded", True):
        with pytest.raises(KeyError, match="Unknown tool"):
            await _dispatch_tool("nonexistent_tool", {})


@pytest.mark.asyncio
async def test_dispatch_triggers_lazy_import_once():
    """Unknown tool triggers import ambrio.tools exactly once."""
    import ambrio.agents.nodes.executor as exc_mod
    exc_mod._tools_loaded = False
    with patch.object(exc_mod, "_tools_loaded", False):
        with patch("builtins.__import__", wraps=__import__) as mock_import:
            with pytest.raises(KeyError):
                await _dispatch_tool("does_not_exist", {})


@pytest.mark.asyncio
async def test_dispatch_none_args_becomes_empty_dict():
    """args=None should be passed as {} to the callable."""
    mock_fn = AsyncMock(return_value="ok")
    _TOOL_REGISTRY["null_args_tool"] = mock_fn
    await _dispatch_tool("null_args_tool", None)
    mock_fn.assert_awaited_once_with({})


def test_register_tool_decorator_returns_original_function():
    async def my_tool(args): return args
    decorated = register_tool("my_tool")(my_tool)
    assert decorated is my_tool
    assert _TOOL_REGISTRY["my_tool"] is my_tool

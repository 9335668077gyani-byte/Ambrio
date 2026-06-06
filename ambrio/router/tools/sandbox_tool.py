# ambrio/router/tools/sandbox_tool.py
from ..tool_registry import tool

_orchestrator = None

def init_sandbox_tool(orchestrator) -> None:
    """Wire the SandboxOrchestrator instance into this tool at service startup."""
    global _orchestrator
    _orchestrator = orchestrator

@tool()
async def run_sandboxed_code(code: str, lang: str) -> dict:
    """Execute code safely in an isolated Docker/gVisor sandbox. Returns stdout, stderr, and verdict."""
    if not _orchestrator:
        return {"error": "sandbox not initialized — Docker may not be available"}
    result = await _orchestrator.execute({
        "type":        "code_exec",
        "payload":     {"code": code, "lang": lang},
        "constraints": {"timeout_s": 30, "network": False}
    })
    return {
        "verdict":  result.verdict,
        "stdout":   result.stdout,
        "stderr":   result.stderr,
        "artifact": result.artifact
    }

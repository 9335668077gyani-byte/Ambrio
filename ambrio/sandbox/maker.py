# ambrio/sandbox/maker.py
import json
from .docker_runner import DockerRunner
from .checker import MakerOutput


class MakerAgent:
    def __init__(self, use_gvisor: bool = True):
        self.runner = DockerRunner(use_gvisor=use_gvisor)

    async def run(self, task: dict) -> MakerOutput:
        payload     = task.get("payload", {})
        code        = payload.get("code", "")
        lang        = payload.get("lang", "python")
        constraints = task.get("constraints", {})
        net         = constraints.get("network", False)
        timeout     = constraints.get("timeout_s", 30)

        # Inject checker feedback as a comment if this is a retry
        if feedback := task.get("_checker_feedback"):
            code = f"# Previous attempt failed: {feedback}\n{code}"

        stdout, stderr, exit_code = await self.runner.run(
            code, lang=lang, network_enabled=net, timeout=timeout
        )

        # Attempt to parse structured JSON artifact from stdout
        artifact: dict = {}
        try:
            artifact = json.loads(stdout)
        except Exception:
            artifact = {"raw": stdout}

        return MakerOutput(
            stdout=stdout,
            stderr=stderr,
            artifact=artifact,
            exit_code=exit_code
        )

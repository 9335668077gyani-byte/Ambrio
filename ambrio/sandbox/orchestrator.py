# ambrio/sandbox/orchestrator.py
from dataclasses import dataclass
from .maker   import MakerAgent
from .checker import CheckerAgent, Verdict


@dataclass
class SandboxResult:
    verdict:  str
    stdout:   str
    stderr:   str
    artifact: dict


class SandboxOrchestrator:
    MAX_RETRIES = 2

    def __init__(self, use_gvisor: bool = True):
        self.maker   = MakerAgent(use_gvisor=use_gvisor)
        self.checker = CheckerAgent()

    async def execute(self, task: dict) -> SandboxResult:
        """
        Maker-Checker loop:
          1. Maker executes task in Docker/gVisor sandbox
          2. Checker grades output (PASS / FAIL / UNSAFE)
          3. UNSAFE → return immediately (no retry)
          4. FAIL   → inject checker feedback, retry up to MAX_RETRIES
          5. PASS   → return result
        """
        for attempt in range(self.MAX_RETRIES + 1):
            maker_out = await self.maker.run(task)
            verdict   = await self.checker.grade(task, maker_out)

            if verdict == Verdict.UNSAFE:
                return SandboxResult(
                    verdict=Verdict.UNSAFE,
                    stdout="", stderr="",
                    artifact={"reason": "checker: unsafe operation detected"}
                )

            if verdict == Verdict.PASS:
                return SandboxResult(
                    verdict=Verdict.PASS,
                    stdout=maker_out.stdout,
                    stderr=maker_out.stderr,
                    artifact=maker_out.artifact
                )

            # FAIL — inject feedback for next attempt
            task["_checker_feedback"] = maker_out.stderr or maker_out.stdout

        return SandboxResult(
            verdict=Verdict.FAIL,
            stdout="", stderr="max retries exceeded",
            artifact={}
        )

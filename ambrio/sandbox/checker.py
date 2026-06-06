# ambrio/sandbox/checker.py
from dataclasses import dataclass
from .policies.allowlist import is_safe_output


class Verdict:
    PASS   = "pass"
    FAIL   = "fail"
    UNSAFE = "unsafe"


@dataclass
class MakerOutput:
    stdout:    str
    stderr:    str
    artifact:  dict
    exit_code: int


class CheckerAgent:
    async def grade(self, task: dict, output: MakerOutput) -> str:
        """
        Returns Verdict.PASS, Verdict.FAIL, or Verdict.UNSAFE.
        UNSAFE short-circuits the retry loop — no retries on unsafe output.
        """
        # 1. Static safety scan on stdout + artifact
        combined = output.stdout + str(output.artifact)
        if not is_safe_output(combined):
            return Verdict.UNSAFE

        # 2. Non-zero exit code = failure (retry eligible)
        if output.exit_code != 0:
            return Verdict.FAIL

        # 3. Task-type specific structural validation
        task_type = task.get("type")
        if task_type == "db_query":
            if not isinstance(output.artifact.get("rows"), list):
                return Verdict.FAIL
        elif task_type == "codegen":
            if not output.artifact.get("code"):
                return Verdict.FAIL

        return Verdict.PASS

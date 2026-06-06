# ambrio/sandbox/docker_runner.py
import asyncio, tempfile
from pathlib import Path
from .policies.resource_limits import LIMITS

SANDBOX_IMAGE  = "ambrio-sandbox:latest"
GVISOR_RUNTIME = "runsc"   # must be registered in /etc/docker/daemon.json

class DockerRunner:
    def __init__(self, use_gvisor: bool = True):
        self.use_gvisor = use_gvisor

    async def run(
        self,
        code: str,
        lang: str = "python",
        network_enabled: bool = False,
        timeout: int = LIMITS["timeout_s"]
    ) -> tuple[str, str, int]:
        """Returns (stdout, stderr, exit_code). Runs code in isolated container."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fname = "main.py" if lang == "python" else "main.sh"
            (Path(tmpdir) / fname).write_text(code, encoding="utf-8")
            cmd = self._build_cmd(tmpdir, lang, network_enabled)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=float(timeout)
                )
            except asyncio.TimeoutError:
                proc.kill()
                return "", "TIMEOUT", 124

        return stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode

    def _build_cmd(self, workdir: str, lang: str, network: bool) -> list[str]:
        cmd = ["docker", "run", "--rm"]
        if self.use_gvisor:
            cmd += ["--runtime", GVISOR_RUNTIME]
        cmd += [
            "--read-only",
            "--tmpfs", "/tmp:size=64m",
            "--network", "bridge" if network else "none",
            "--cpus",       LIMITS["cpus"],
            "--memory",     LIMITS["memory"],
            "--pids-limit", str(LIMITS["pids"]),
            "-v", f"{workdir}:/work:ro",
            SANDBOX_IMAGE,
        ]
        if lang == "python":
            cmd += ["python", "/work/main.py"]
        else:
            cmd += ["bash", "/work/main.sh"]
        return cmd

"""Own two warm local RPent model services for a serial evaluation run."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace/vla_baselines"


def _port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return handle.getsockname()[1]


class SharedModelServices:
    """Start only VLA/SAM3; each episode still owns a fresh environment."""

    def __init__(self, output: Path):
        self.output = output
        self.processes = {}
        self.handles = []
        self.endpoints = {name: f"http://127.0.0.1:{_port()}" for name in ("vla", "sam3")}
        self.report = {"status": "starting", "endpoints": self.endpoints, "processes": {}, "cleanup_exit_codes": {}}

    def _save(self):
        temporary = self.output / "services-summary.tmp"
        temporary.write_text(json.dumps(self.report, indent=2) + "\n")
        temporary.replace(self.output / "services-summary.json")

    def _ready(self, name: str, timeout: float = 300):
        process = self.processes[name]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(self.endpoints[name] + "/call", data=b'{"method":"healthz","args":[],"kwargs":{}}', headers={"Content-Type": "application/json"})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"owned {name} service exited before readiness")
            try:
                with opener.open(request, timeout=2) as response:
                    if json.load(response).get("ok"):
                        return
            except OSError:
                pass
            time.sleep(0.5)
        raise TimeoutError(f"owned {name} service readiness timed out")

    def start(self) -> dict[str, str]:
        self.output.mkdir(parents=True, exist_ok=False)
        self.report["started_at_utc"] = datetime.now(timezone.utc).isoformat()
        self._save()
        # Imported only in explicit execution mode, never by a plan or unit test.
        from smoke_environment import source_environment
        environment = source_environment(self.output, "standard")
        environment.pop("DEEPSEEK_API_KEY", None)
        environment.pop("LIBERO_SUFFIX", None)
        environment.pop("LIBERO_PERTURBATION", None)
        environment.update(JAX_PLATFORMS="cpu", CUDA_VISIBLE_DEVICES="0", OPENPI_DATA_HOME=str(WORKSPACE / "cache/openpi"),
                           HF_HOME=str(WORKSPACE / "cache/huggingface"), PI05_CHECKPOINT_PATH=str(WORKSPACE / "checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT"),
                           SAM3_CHECKPOINT_PATH=str(WORKSPACE / "checkpoints/sam3/sam3.pt"), RPENT_REPO_ROOT=str(WORKSPACE / "repos/rpent"),
                           RPENT_RLINF_ROOT=str(WORKSPACE / "repos/harness-rlinf"))
        commands = {
            "vla": [str(WORKSPACE / ".venvs/harness-vla/bin/python"), str(ROOT / "scripts/vla/run_harness_vla.py"), "serve", "--output", str(self.output / "vla-inference.json"), "--port", self.endpoints["vla"].rsplit(":", 1)[1], "--parent-watch"],
            "sam3": [str(WORKSPACE / ".venvs/harness-sam3/bin/python"), "-m", "rpent.robots.components.sam3_server", "--transport", "http", "--host", "127.0.0.1", "--port", self.endpoints["sam3"].rsplit(":", 1)[1], "--parent-watch", "--cuda-device", "0"],
        }
        try:
            for name, command in commands.items():
                env = environment.copy()
                env["PYTHONPATH"] = os.pathsep.join(str(WORKSPACE / "repos" / p) for p in ("rpent", "harness-rlinf")) + os.pathsep + str(WORKSPACE / "repos/harness-openpi/src") if name == "vla" else str(WORKSPACE / "repos/rpent") + os.pathsep + str(WORKSPACE / "repos/harness-sam3")
                handle = (self.output / f"{name}.log").open("wb")
                self.handles.append(handle)
                process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
                self.processes[name] = process
                self.report["processes"][name] = {"pid": process.pid, "command": command}
                self.report["stage"] = f"starting_{name}"
                self._save()
                self._ready(name)
            self.report.update(status="ready", stage="ready")
            self._save()
            return dict(self.endpoints)
        except BaseException:
            self.close()
            raise

    def alive(self) -> bool:
        return len(self.processes) == 2 and all(p.poll() is None for p in self.processes.values())

    def close(self):
        for name, process in reversed(list(self.processes.items())):
            if process.poll() is None:
                try:
                    request = urllib.request.Request(self.endpoints[name] + "/call", data=b'{"method":"shutdown","args":[],"kwargs":{}}', headers={"Content-Type": "application/json"})
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with opener.open(request, timeout=3) as response:
                        response.read()
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=10)
                except ProcessLookupError:
                    pass
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            self.report["cleanup_exit_codes"][name] = process.poll()
        for handle in self.handles:
            handle.close()
        self.handles.clear()
        self.report.update(status="stopped", finished_at_utc=datetime.now(timezone.utc).isoformat())
        if self.output.is_dir():
            self._save()

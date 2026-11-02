#!/usr/bin/env python3
"""Start isolated RPent services and attempt one standard LIBERO or Pro task."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace/vla_baselines"


def free_port() -> int:
    with socket.socket() as handle:
        handle.bind(("127.0.0.1", 0))
        return handle.getsockname()[1]


def wait_ready(endpoint: str, process: subprocess.Popen, timeout: float = 300) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    request = urllib.request.Request(endpoint + "/call", data=json.dumps({"method": "healthz", "args": [], "kwargs": {}}).encode(), headers={"Content-Type": "application/json"})
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"service exited with code {process.returncode}: {endpoint}")
        try:
            with opener.open(request, timeout=2) as response:
                if json.load(response).get("ok"):
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"service readiness timed out: {endpoint}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--components-only", action="store_true")
    parser.add_argument("--planner-timeout-s", type=int, default=1200)
    parser.add_argument("--reasoning-effort", choices=("none", "low", "medium", "high", "xhigh", "max"), default="medium")
    parser.add_argument("--suite", default="libero_object_swap")
    parser.add_argument("--libero-type", choices=("standard", "pro"), default="pro")
    parser.add_argument("--task", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-episode-steps", type=int, default=10000)
    parser.add_argument("--max-turns", type=int, default=100)
    parser.add_argument("--max-tokens", type=int, default=10000)
    parser.add_argument("--configuration-version", default=None)
    parser.add_argument("--planner", choices=("codex", "api"), default="codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--max-cost-usd", type=float, help="API request cost reservation limit, enforced before each HTTP attempt")
    parser.add_argument("--budget-ledger", type=Path, help="Persistent cumulative ledger reused across recovery attempts")
    parser.add_argument("--skip-component-checks", action="store_true", help="Reuse the already-passed component validation")
    parser.add_argument("--vla-endpoint", default=None, help="Reuse an already-running VLA service; do not stop it.")
    parser.add_argument("--sam3-endpoint", default=None, help="Reuse an already-running SAM3 service; do not stop it.")
    parser.add_argument("--disable-compile", action="store_true")
    return parser


def planner_command(args, output: Path, endpoints: dict[str, str]) -> list[str]:
    memory = WORKSPACE / "cache/harness-assets-download/memory/7db66088d06d04ae097682332a09704f13e6fc0c/GPT_5.5_xhigh"
    if args.planner == "api":
        command = [str(WORKSPACE / ".venvs/harness-rpent/bin/python"), str(ROOT / "scripts/harness/deepseek_api.py")]
    else:
        command = [str(WORKSPACE / ".venvs/harness-rpent/bin/rpent")]
    command += ["--robot", "libero", "--libero-type", args.libero_type, "--suite", args.suite,
                "--task", str(args.task), "--seed", str(args.seed),
                "--max-episode-steps", str(args.max_episode_steps), "--cuda-device", "0",
                "--planner", args.planner, "--reasoning-effort", args.reasoning_effort,
                "--max-turns", str(args.max_turns), "--max-tokens", str(args.max_tokens),
                "--planner-timeout-s", str(args.planner_timeout_s), "--memory-profile", "local",
                "--memory-dir", str(memory), "--output-dir", str(output / "online-task")]
    if args.model:
        command += ["--model", args.model]
    if args.base_url:
        command += ["--base-url", args.base_url]
    command += [part for name, endpoint in endpoints.items() for part in ("--" + name + "-endpoint", endpoint)]
    return command


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.task < 0 or args.seed < 0 or min(args.max_episode_steps, args.max_turns, args.max_tokens, args.planner_timeout_s) <= 0:
        parser.error("task/seed must be nonnegative and budgets must be positive")
    if args.planner == "api":
        if args.model != "deepseek:deepseek-flash" or args.base_url != "https://api.deepseek.com":
            parser.error("this API entry requires --model deepseek:deepseek-flash --base-url https://api.deepseek.com")
        if not args.components_only and not os.environ.get("DEEPSEEK_API_KEY"):
            parser.error("DEEPSEEK_API_KEY must be supplied in the process environment; no key file is read")
        if not args.components_only and (args.max_cost_usd is None or not math.isfinite(args.max_cost_usd) or args.max_cost_usd <= 0):
            parser.error("API execution requires a positive --max-cost-usd request reservation limit")
    elif args.base_url:
        parser.error("--base-url is only supported with --planner api")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT / "scripts/harness"))
    from smoke_environment import source_environment
    env = source_environment(output, args.libero_type)
    if args.planner == "api" and args.max_cost_usd is not None:
        env["DEEPSEEK_MAX_COST_USD"] = str(args.max_cost_usd)
        env["DEEPSEEK_BUDGET_REPORT_PATH"] = str(args.budget_ledger.resolve() if args.budget_ledger else Path(env.get("DEEPSEEK_BUDGET_REPORT_PATH", str(output / "deepseek-budget.json"))).resolve())
        if args.configuration_version:
            env["DEEPSEEK_CONFIG_VERSION"] = args.configuration_version
    # These inherited overrides otherwise change which benchmark assets RLinf uses.
    env.pop("LIBERO_SUFFIX", None)
    env.pop("LIBERO_PERTURBATION", None)
    env.update(
        JAX_PLATFORMS="cpu", CUDA_VISIBLE_DEVICES="0",
        OPENPI_DATA_HOME=str(WORKSPACE / "cache/openpi"),
        HF_HOME=str(WORKSPACE / "cache/huggingface"),
        PI05_CHECKPOINT_PATH=str(WORKSPACE / "checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT"),
        SAM3_CHECKPOINT_PATH=str(WORKSPACE / "checkpoints/sam3/sam3.pt"),
        RPENT_REPO_ROOT=str(WORKSPACE / "repos/rpent"),
        RPENT_RLINF_ROOT=str(WORKSPACE / "repos/harness-rlinf"),
    )
    endpoints = {name: f"http://127.0.0.1:{free_port()}" for name in ("env", "vla", "sam3")}
    if args.vla_endpoint:
        endpoints["vla"] = args.vla_endpoint
    if args.sam3_endpoint:
        endpoints["sam3"] = args.sam3_endpoint
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "status": "starting", "stage": "prepare", "task": {"libero_type": args.libero_type, "suite": args.suite, "task": args.task, "seed": args.seed, "max_episode_steps": args.max_episode_steps}, "endpoints": endpoints, "torch_compile": not args.disable_compile, "reasoning_effort": args.reasoning_effort, "planner": args.planner, "model": args.model, "base_url": args.base_url, "api_cost_limit_usd": args.max_cost_usd, "max_tokens": args.max_tokens, "configuration_version": args.configuration_version, "commands": {}}
    processes: dict[str, subprocess.Popen] = {}
    handles = []
    stop_sampling = threading.Event()

    def save() -> None:
        temporary = output / "run-summary.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(output / "run-summary.json")

    def sample_gpu() -> None:
        with (output / "gpu-memory.csv").open("w") as handle:
            handle.write("unix_seconds,memory_total_mib,memory_used_mib,memory_free_mib\n")
            while not stop_sampling.is_set():
                sample = subprocess.run(["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
                if sample.returncode == 0:
                    handle.write(f"{time.time():.3f},{sample.stdout.strip()}\n")
                    handle.flush()
                stop_sampling.wait(0.5)

    def start(name: str, command: list[str], environment: dict) -> None:
        report["stage"] = "starting_" + name
        report["commands"][name] = command
        save()
        handle = (output / f"{name}-server.log").open("wb")
        handles.append(handle)
        processes[name] = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.PIPE, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
        wait_ready(endpoints[name], processes[name])
        print(f"{name} ready at {endpoints[name]}", flush=True)

    sampler = threading.Thread(target=sample_gpu, daemon=True)
    sampler.start()
    save()
    try:
        main_python = str(WORKSPACE / ".venvs/harness-rpent/bin/python")
        service_env = env.copy()
        service_env.pop("DEEPSEEK_API_KEY", None)
        start("env", [main_python, "-m", "robots.libero.env_server", "--suite", args.suite, "--task", str(args.task), "--seed", str(args.seed), "--max-episode-steps", str(args.max_episode_steps), "--transport", "http", "--host", "127.0.0.1", "--port", endpoints["env"].rsplit(":", 1)[1], "--parent-watch"], service_env)
        vla_env = env.copy()
        vla_env.pop("DEEPSEEK_API_KEY", None)
        vla_env["PYTHONPATH"] = os.pathsep.join(str(WORKSPACE / "repos" / name) for name in ("rpent", "harness-rlinf")) + os.pathsep + str(WORKSPACE / "repos/harness-openpi/src")
        vla_command = [str(WORKSPACE / ".venvs/harness-vla/bin/python"), str(ROOT / "scripts/vla/run_harness_vla.py"), "serve", "--output", str(output / "vla-inference.json"), "--port", endpoints["vla"].rsplit(":", 1)[1], "--parent-watch"]
        if args.disable_compile:
            vla_command.append("--disable-compile")
        if not args.vla_endpoint:
            start("vla", vla_command, vla_env)
        sam_env = env.copy()
        sam_env.pop("DEEPSEEK_API_KEY", None)
        sam_env["PYTHONPATH"] = str(WORKSPACE / "repos/rpent") + os.pathsep + str(WORKSPACE / "repos/harness-sam3")
        if not args.sam3_endpoint:
            start("sam3", [str(WORKSPACE / ".venvs/harness-sam3/bin/python"), "-m", "rpent.robots.components.sam3_server", "--transport", "http", "--host", "127.0.0.1", "--port", endpoints["sam3"].rsplit(":", 1)[1], "--parent-watch", "--cuda-device", "0"], sam_env)
        endpoint_args = [part for name, endpoint in endpoints.items() for part in ("--" + name + "-endpoint", endpoint)]
        if not args.skip_component_checks:
            report["stage"] = "component_checks"
            save()
            component_command = [main_python, str(ROOT / "scripts/vla/check_harness_components.py"), "--output-dir", str(output / "components"), "--suite", args.suite, "--task", str(args.task), "--seed", str(args.seed), "--libero-type", args.libero_type, *endpoint_args]
            report["commands"]["component_checks"] = component_command
            with (output / "component-checks.log").open("wb") as handle:
                subprocess.run(component_command, cwd=ROOT, env=service_env, stdout=handle, stderr=subprocess.STDOUT, timeout=300, check=True)
            report["component_checks"] = json.loads((output / "components/result.json").read_text())
            print("component checks passed", flush=True)
        else:
            report["component_checks"] = {"status": "previous_validation_reused"}
        if args.components_only:
            report.update(status="passed", stage="component_checks_complete")
            return 0
        memory = WORKSPACE / "cache/harness-assets-download/memory/7db66088d06d04ae097682332a09704f13e6fc0c/GPT_5.5_xhigh"
        if not (memory / "MEMORY.md").is_file():
            raise FileNotFoundError("pinned planner memory is missing")
        command = planner_command(args, output, endpoints)
        report.update(stage="online_planner_running")
        report["commands"]["online_planner"] = command
        save()
        with (output / "planner.log").open("wb") as handle:
            processes["planner"] = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
            code = processes["planner"].wait(timeout=args.planner_timeout_s + 120)
        transcripts = sorted((output / "online-task").glob("transcript_*.json"))
        if len(transcripts) != 1:
            raise RuntimeError(f"expected one planner transcript, found {len(transcripts)}; exit={code}")
        transcript = json.loads(transcripts[0].read_text())
        # This fixed LIBERO spec lacks finalize_run, so the upstream transcript
        # leaves environment_success null. Read its native per-step trace;
        # never infer success from the planner's finish prose or from a recipe.
        state_path = output / "online-task/states.json"
        state = json.loads(state_path.read_text())
        steps = state.get("steps")
        if not isinstance(steps, list) or not steps or any(type(step.get("terminated")) is not bool for step in steps):
            raise RuntimeError("native environment trace is missing valid terminal flags")
        terminated_steps = [step["step_idx"] for step in steps if step["terminated"]]
        native_success = bool(terminated_steps)
        report.update(stage="online_task_complete", planner_exit_code=code, transcript=str(transcripts[0]), upstream_environment_success=transcript.get("environment_success"), environment_success=native_success, native_success_evidence={"path": str(state_path), "terminated_step_indices": terminated_steps, "state_record_count": len(steps)}, planner_finish=transcript.get("finish"), planner_error=transcript.get("error"), planner_stats=transcript.get("stats"), elapsed_s=transcript.get("elapsed_s"))
        if code != 0 or transcript.get("error"):
            report["status"] = "planner_error"
        else:
            report["status"] = "passed" if native_success else "task_unsuccessful"
        return 0 if report["status"] == "passed" else 1
    except (Exception, KeyboardInterrupt) as exc:
        report.update(status="failed", error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
        traceback.print_exc()
        return 1
    finally:
        cleanup = {}
        cleanup_errors = []
        for name, process in reversed(list(processes.items())):
            try:
                if process.poll() is None and name in endpoints:
                    try:
                        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                        request = urllib.request.Request(endpoints[name] + "/call", data=json.dumps({"method": "shutdown", "args": [], "kwargs": {}}).encode(), headers={"Content-Type": "application/json"})
                        with opener.open(request, timeout=3) as response:
                            json.load(response)
                        process.wait(timeout=5)
                    except (OSError, ValueError, subprocess.TimeoutExpired):
                        pass
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=5)
            except Exception as exc:
                cleanup_errors.append({"service": name, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                cleanup[name] = process.poll()
        for handle in handles:
            handle.close()
        stop_sampling.set()
        sampler.join(timeout=6)
        report["cleanup_exit_codes"] = cleanup
        report["cleanup_errors"] = cleanup_errors
        if any(code is None for code in cleanup.values()):
            report["task_status_before_cleanup"] = report["status"]
            report["status"] = "cleanup_failed"
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        save()
        print(json.dumps({key: report.get(key) for key in ("status", "stage", "environment_success", "error")}), flush=True)
        if report["status"] == "cleanup_failed":
            return 1


if __name__ == "__main__":
    raise SystemExit(main())

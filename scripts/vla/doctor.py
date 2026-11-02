#!/usr/bin/env python3
"""Read-only deployment inventory for OpenVLA and pi0.5.

Only the Python standard library is used. Frameworks are inspected through
distribution metadata and top-level module discovery; they are never imported.
Exit status 0 means the inventory ran, not that a model deployment passed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKSPACE = REPOSITORY_ROOT / "workspace" / "vla_baselines"


def run_command(arguments: list[str], timeout: float = 15.0) -> dict:
    """Run a fixed inventory command, preserving failures in the report."""
    try:
        result = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "error", "error": str(exc)}
    report = {
        "status": "ok" if result.returncode == 0 else "error",
        "return_code": result.returncode,
        "stdout": result.stdout.strip(),
    }
    if result.stderr.strip():
        report["stderr"] = result.stderr.strip()[:2000]
    return report


def numeric_value(value: str) -> float | None:
    try:
        return float(value.strip())
    except ValueError:
        return None


def gpu_inventory() -> dict:
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return {"status": "unavailable", "error": "nvidia-smi not found", "devices": []}

    base_fields = ["name", "driver_version", "memory.total", "memory.free"]
    attempts = []
    for compute_cap_requested in (True, False):
        fields = base_fields + (["compute_cap"] if compute_cap_requested else [])
        result = run_command(
            [executable, "--query-gpu=" + ",".join(fields), "--format=csv,noheader,nounits"]
        )
        output = result.pop("stdout", "")
        attempts.append({"fields": fields, **result})
        if result["status"] != "ok":
            continue

        devices = []
        parse_errors = []
        for line in output.splitlines():
            values = [value.strip() for value in line.split(",")]
            if len(values) != len(fields):
                parse_errors.append("Unexpected GPU inventory column count")
                continue
            total_mib = numeric_value(values[2])
            free_mib = numeric_value(values[3])
            devices.append(
                {
                    "name": values[0],
                    "driver_version": values[1],
                    "memory_total_mib": total_mib,
                    "memory_free_mib": free_mib,
                    "memory_used_mib": (
                        max(0.0, total_mib - free_mib)
                        if total_mib is not None and free_mib is not None
                        else None
                    ),
                    "compute_capability": (
                        values[4] if compute_cap_requested and numeric_value(values[4]) is not None
                        else None
                    ),
                }
            )
        report = {
            "status": "partial" if parse_errors or not compute_cap_requested else "ok",
            "executable": executable,
            "compute_capability_query_supported": compute_cap_requested,
            "devices": devices,
            "attempts": attempts,
        }
        if parse_errors:
            report["errors"] = parse_errors
        if not compute_cap_requested:
            report["note"] = "GPU query succeeded without compute_cap; architecture needs confirmation."
        return report
    return {"status": "error", "executable": executable, "devices": [], "attempts": attempts}


def cuda_toolkit_inventory() -> dict:
    executable = shutil.which("nvcc")
    if executable is None:
        return {
            "status": "unavailable",
            "error": "nvcc not found on PATH; this does not rule out CUDA-enabled framework wheels.",
        }
    result = run_command([executable, "--version"])
    output = result.pop("stdout", "")
    match = re.search(r"release\s+([\d.]+)", output)
    return {
        "executable": executable,
        **result,
        "toolkit_release": match.group(1) if match else None,
        "version_output": output[:2000],
    }


def ram_inventory() -> dict:
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            values = {}
            for line in meminfo.read_text(encoding="utf-8").splitlines():
                key, _, value = line.partition(":")
                if key in {"MemTotal", "MemAvailable", "MemFree"}:
                    values[key] = int(value.split()[0]) * 1024
            return {
                "status": "ok",
                "source": "/proc/meminfo",
                "total_bytes": values.get("MemTotal"),
                "available_bytes": values.get("MemAvailable"),
                "free_bytes": values.get("MemFree"),
            }
        except (OSError, ValueError, IndexError) as exc:
            return {"status": "error", "error": str(exc)}
    return {"status": "unavailable", "error": "RAM inventory currently supports Linux /proc/meminfo."}


def disk_inventory(workspace: Path) -> dict:
    measured_path = workspace
    try:
        while not measured_path.is_dir() and measured_path != measured_path.parent:
            measured_path = measured_path.parent
        usage = shutil.disk_usage(measured_path)
        return {
            "status": "ok",
            "requested_workspace": str(workspace),
            "workspace_exists": workspace.exists(),
            "workspace_is_directory": workspace.is_dir(),
            "measured_path": str(measured_path),
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "workspace_created": False,
        }
    except OSError as exc:
        return {"status": "error", "requested_workspace": str(workspace), "error": str(exc)}


def tool_inventory() -> dict:
    tools = {
        name: {"path": shutil.which(name)}
        for name in ("uv", "conda", "docker", "git", "ssh", "rsync", "scp", "tmux")
    }
    for info in tools.values():
        info["status"] = "available" if info["path"] else "unavailable"
    docker = tools["docker"]["path"]
    if docker:
        result = run_command([docker, "compose", "version"])
        version_output = result.pop("stdout", "")
        tools["docker_compose"] = {**result, "available": result["status"] == "ok"}
        if version_output:
            tools["docker_compose"]["version_output"] = version_output[:1000]
    else:
        tools["docker_compose"] = {
            "status": "unavailable",
            "available": False,
            "error": "docker not found; Compose availability cannot be checked.",
        }
    return tools


def package_inventory() -> dict:
    candidates = {
        "torch": "torch",
        "torchvision": "torchvision",
        "jax": "jax",
        "jaxlib": "jaxlib",
        "transformers": "transformers",
        "timm": "timm",
        "tensorflow": "tensorflow",
        "flax": "flax",
        "orbax-checkpoint": "orbax",
        "accelerate": "accelerate",
        "safetensors": "safetensors",
        "numpy": "numpy",
        "openpi": "openpi",
        "openvla": "openvla",
        "prismatic": "prismatic",
    }
    packages = {}
    for distribution, module in candidates.items():
        report = {"module": module, "version": None, "module_discoverable": False}
        try:
            report["version"] = importlib.metadata.version(distribution)
            report["distribution_status"] = "installed"
        except importlib.metadata.PackageNotFoundError:
            report["distribution_status"] = "not_found"
        except Exception as exc:
            report["distribution_status"] = "error"
            report["metadata_error"] = str(exc)
        try:
            report["module_discoverable"] = importlib.util.find_spec(module) is not None
        except Exception as exc:
            report["module_discovery_error"] = str(exc)
        packages[distribution] = report
    return {
        "scope": "current_interpreter_only",
        "inspection": "distribution metadata and top-level find_spec; no framework imports",
        "packages": packages,
    }


def observations(gpus: dict) -> list[dict]:
    notes = [
        {
            "code": "sixteen_gib_inference_candidate",
            "message": (
                "For this deployment preparation, a GPU with approximately 16 GiB is only an inference "
                "candidate. Model loading and inference memory must be measured before acceptance; "
                "fine-tuning or external RL training capacity is not established."
            ),
        },
        {
            "code": "respect_active_gpu_work",
            "message": (
                "Occupied GPU memory may belong to active programs. Do not stop other programs to "
                "make space; coordinate available capacity before running model tests."
            ),
        },
        {
            "code": "blackwell_wheel_architecture",
            "message": (
                "Blackwell GPUs require confirmation that the selected torch/jax CUDA wheels support "
                "the GPU architecture. Driver and nvcc versions alone do not establish compatibility."
            ),
        },
        {
            "code": "interpreter_scope",
            "message": (
                "A missing package in this interpreter does not mean it is missing from all conda "
                "environments. Re-run the inventory with the intended deployment interpreter."
            ),
        },
        {
            "code": "inventory_is_not_acceptance",
            "message": (
                "This is inventory_only. Exit status 0 confirms report generation, not model deployment, "
                "simulator connectivity, rollout correctness, or RL training acceptance."
            ),
        },
    ]
    for index, gpu in enumerate(gpus.get("devices", [])):
        total_mib = gpu.get("memory_total_mib")
        compute = gpu.get("compute_capability")
        name = gpu.get("name", "")
        if total_mib is not None and 14000 <= total_mib <= 18000:
            notes.append({"code": "observed_sixteen_gib_gpu", "gpu_index": index, "memory_total_mib": total_mib})
        if "blackwell" in name.lower() or (compute and float(compute) >= 10):
            notes.append({"code": "observed_blackwell_or_newer", "gpu_index": index, "name": name, "compute_capability": compute})
    return notes


def inventory(workspace: Path) -> dict:
    gpus = gpu_inventory()
    return {
        "report_kind": "inventory_only",
        "deployment_accepted": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "system": {
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "python_executable": sys.executable,
            "python_prefix": sys.prefix,
        },
        "gpu": gpus,
        "cuda_toolkit": cuda_toolkit_inventory(),
        "ram": ram_inventory(),
        "disk": disk_inventory(workspace),
        "tools": tool_inventory(),
        "frameworks": package_inventory(),
        "observations": observations(gpus),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE, help="Target workspace to assess; it is never created.")
    parser.add_argument("--output", type=Path, help="Save the inventory as JSON at this path.")
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    report = inventory(workspace)
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        try:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
        except OSError as exc:
            report["output_error"] = str(exc)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 1
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

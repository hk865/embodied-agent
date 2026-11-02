#!/usr/bin/env python3
"""Exercise an owned RPent LIBERO-Pro RPC service without a learned policy."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import traceback

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace/vla_baselines"
SOURCES = WORKSPACE / "repos"


def array_check(value: object, expected_shape: tuple[int, ...] | None = None) -> dict:
    array = np.asarray(value)
    finite = bool(np.isfinite(array).all())
    result = {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "finite": finite,
        "size": int(array.size),
    }
    if array.size:
        result.update(min=float(array.min()), max=float(array.max()))
    if expected_shape is not None:
        result["expected_shape"] = list(expected_shape)
        if array.shape != expected_shape:
            raise ValueError(f"shape {array.shape} != {expected_shape}")
    if not finite or not array.size:
        raise ValueError(f"invalid numeric array: {result}")
    return result


def obs_checks(obs: dict) -> dict:
    return {
        "main_images": array_check(obs["main_images"], (256, 256, 3)),
        "wrist_images": array_check(obs["wrist_images"], (256, 256, 3)),
        "states": array_check(obs["states"], (8,)),
    }


def source_environment(output: Path, libero_type: str = "pro") -> dict[str, str]:
    if libero_type not in ("pro", "standard"):
        raise ValueError("libero_type must be pro or standard")
    config = output / "libero-config"
    config.mkdir()
    core = SOURCES / ("harness-liberopro/liberopro/liberopro" if libero_type == "pro" else "harness-libero/libero/libero")
    paths = {
        "benchmark_root": str(core),
        "bddl_files": str(core / "bddl_files"),
        "init_states": str(core / "init_files"),
        "assets": str(core / "assets"),
        "datasets": str(output / "unused-datasets"),
    }
    (config / "config.yaml").write_text(json.dumps(paths, indent=2) + "\n")
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.update(
        PYTHONPATH=os.pathsep.join(
            str(SOURCES / repo)
            for repo in ("rpent", "harness-rlinf", "harness-liberopro", "harness-libero")
        ),
        PYTHONDONTWRITEBYTECODE="1",
        LIBERO_CONFIG_PATH=str(config),
        LIBERO_TYPE=libero_type,
        MUJOCO_GL="egl",
        PYOPENGL_PLATFORM="egl",
        ROBOT_PLATFORM="LIBERO",
        MPLCONFIGDIR=str(output / "matplotlib-cache"),
        NUMBA_CACHE_DIR=str(output / "numba-cache"),
        TMPDIR=str(output / "tmp"),
        OMP_NUM_THREADS="1",
        OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
    )
    Path(environment["TMPDIR"]).mkdir()
    return environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="libero_object_swap")
    parser.add_argument("--task", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-episode-steps", type=int, default=220)
    parser.add_argument("--timeout-s", type=float, default=240)
    parser.add_argument("--server-python", default=str(WORKSPACE / ".venvs/harness-rpent/bin/python"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = args.output_dir or WORKSPACE / "artifacts/harness-2026-10-06" / (
        "environment-smoke-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    output = output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("--output-dir must be a new or empty directory")
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    report = {
        "status": "running",
        "scope": "environment_rpc_smoke_only_no_model_or_task_success_claim",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "suite": args.suite,
        "task": args.task,
        "seed": args.seed,
        "source_receipts": {
            repo: json.loads((SOURCES / repo / ".source-receipt.json").read_text())
            for repo in ("rpent", "harness-rlinf", "harness-libero", "harness-liberopro")
        },
        "packages": {
            package: importlib.metadata.version(package)
            for package in ("rpent", "torch", "mujoco", "robosuite", "rpent-libero", "rpent-liberopro")
        },
    }
    process = None
    rpc = None
    try:
        environment = source_environment(output)
        # Imports for the client resolve only the pinned RPent snapshot.
        sys.path.insert(0, str(SOURCES / "rpent"))
        from robots.libero.env_client import LiberoEnvClient
        from rpent.utils.rpc import make_rpc_client, wait_for_ready

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        endpoint = f"socket://127.0.0.1:{port}"
        meta = {
            "suite": args.suite,
            "task": args.task,
            "seed": args.seed,
            "max_episode_steps": args.max_episode_steps,
        }
        command = [
            args.server_python, "-m", "robots.libero.env_server",
            "--transport", "socket", "--host", "127.0.0.1", "--port", str(port),
            "--suite", args.suite, "--task", str(args.task), "--seed", str(args.seed),
            "--max-episode-steps", str(args.max_episode_steps), "--parent-watch",
        ]
        report.update(endpoint=endpoint, server_command=command, source_pythonpath=environment["PYTHONPATH"])
        with (output / "environment-server.log").open("wb") as log:
            process = subprocess.Popen(
                command, cwd=SOURCES / "rpent", env=environment,
                stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        process.name = "owned LIBERO-Pro server"
        rpc = make_rpc_client(endpoint)
        wait_for_ready(rpc, timeout_s=args.timeout_s, daemon=process)
        report["healthz"] = rpc.call("healthz", timeout_s=5)
        client = LiberoEnvClient(rpc, expected_meta=meta)
        report["env_meta"] = rpc.call("env.get_env_meta", timeout_s=5)
        report["task_language"] = client.get_task_language()
        report["initial_observation"] = obs_checks(client.last_obs)
        raw = client.raw_obs()
        report["raw_robot_state"] = {
            key: array_check(raw[key], expected_shape)
            for key, expected_shape in (
                ("robot0_eef_pos", (3,)),
                ("robot0_eef_quat", (4,)),
                ("robot0_gripper_qpos", (2,)),
            )
        }
        camera = client.get_camera_meta("agentview", height=256, width=256)
        report["camera_metadata"] = camera
        report["camera_checks"] = {
            "intrinsic_K": array_check(camera["intrinsic_K"], (3, 3)),
            "extrinsic_cam2world": array_check(camera["extrinsic_cam2world"], (4, 4)),
        }
        if not (0 < camera["depth_near"] < camera["depth_far"]):
            raise ValueError("invalid camera depth planes")
        rgb, depth = client.render_camera("agentview", height=256, width=256, depth=True)
        report["render_rgb"] = array_check(rgb, (256, 256, 3))
        report["render_depth"] = array_check(depth, (256, 256))
        report["depth_representation"] = "MuJoCo normalized z-buffer; near/far planes saved in camera_metadata"
        if np.asarray(rgb).dtype != np.uint8 or np.asarray(rgb).std() == 0:
            raise ValueError("RGB frame is not nonempty uint8")
        if not (0 <= np.asarray(depth).min() < np.asarray(depth).max() <= 1):
            raise ValueError("rendered depth has no valid scene variation")
        frame = output / "environment-agentview-256.png"
        Image.fromarray(np.asarray(rgb)[::-1].copy()).save(frame)
        report.update(frame_path=str(frame), frame_orientation="native sim.render vertically flipped, matching RPent capture")
        np.save(output / "environment-depth-256.npy", np.asarray(depth), allow_pickle=False)
        report["steps"] = []
        action = np.array([0, 0, 0, 0, 0, 0, -1], dtype=np.float32)
        report["action_check"] = array_check(action, (7,))
        for step_index in range(2):
            obs, reward, term, trunc, _ = client.step(action)
            report["steps"].append({
                "step": step_index + 1, "observation": obs_checks(obs),
                "reward": float(np.asarray(reward)),
                "terminated": bool(np.asarray(term).any()),
                "truncated": bool(np.asarray(trunc).any()),
            })
            if client.terminated or client.truncated:
                break
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="error", error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
    finally:
        if rpc is not None:
            try:
                rpc.call("shutdown", timeout_s=5)
                report["shutdown_rpc"] = "accepted"
            except Exception as exc:
                report["shutdown_rpc"] = type(exc).__name__
            try:
                rpc.close()
            except Exception as exc:
                report["client_close_error"] = type(exc).__name__
        if process is not None:
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            report["server_exit_code"] = process.returncode
            if report["status"] == "passed" and process.returncode != 0:
                report.update(status="error", error="server did not close cleanly")
        report["elapsed_s"] = round(time.monotonic() - started, 3)
        destination = output / "environment-rpc-smoke.json"
        destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": report["status"], "report": str(destination)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run a small pi0.5 LIBERO evaluation against the local policy service.

Uses the pinned official LIBERO initial states, openpi image preprocessing,
10 stabilization steps, and five actions per policy query. Operational errors
are recorded separately and cause a nonzero exit, never a task-failure rate.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import traceback

sys.dont_write_bytecode = True
from smoke_libero import LIBERO_REPOSITORY, WORKSPACE, quaternion_to_axis_angle


MAX_POLICY_STEPS = {"libero_spatial": 220, "libero_object": 280, "libero_goal": 300, "libero_10": 520}
ARTIFACT_ROOT = WORKSPACE / "artifacts" / "pi05-2026-10-06"


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def source_provenance() -> dict:
    sources = {}
    for name, repository in (("libero", LIBERO_REPOSITORY), ("openpi_client", WORKSPACE / "repos" / "openpi")):
        receipt_path = repository / ".source-receipt.json"
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            sources[name] = {
                "url": receipt["url"],
                "commit": receipt["commit"],
                "receipt_path": str(receipt_path),
                "method": receipt.get("method"),
                "verification": "pinned_source_receipt; not a fresh file-integrity audit",
            }
            if name == "openpi_client":
                sources[name]["package_source"] = str(repository / "packages" / "openpi-client")
        except (OSError, ValueError, KeyError) as exc:
            sources[name] = {"status": "unavailable", "receipt_path": str(receipt_path), "error": str(exc)}
    return sources


def configure_paths(output: Path) -> Path:
    benchmark_root = LIBERO_REPOSITORY / "libero" / "libero"
    config_directory = output / "libero-config"
    config_directory.mkdir(exist_ok=True)
    unused_datasets = output / "libero-unused-datasets"
    unused_datasets.mkdir(exist_ok=True)
    write_json(config_directory / "config.yaml", {
        "benchmark_root": str(benchmark_root),
        "bddl_files": str(benchmark_root / "bddl_files"),
        "init_states": str(benchmark_root / "init_files"),
        "datasets": str(unused_datasets),
        "assets": str(benchmark_root / "assets"),
    })
    os.environ["LIBERO_CONFIG_PATH"] = str(config_directory)
    os.environ["MUJOCO_GL"] = "egl"
    os.environ["MPLCONFIGDIR"] = str(output / "libero-matplotlib-cache")
    os.environ["NUMBA_CACHE_DIR"] = str(output / "libero-numba-cache")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(LIBERO_REPOSITORY))
    return benchmark_root


def policy_input(observation, instruction, np, image_tools) -> dict:
    images = {}
    for key in ("agentview_image", "robot0_eye_in_hand_image"):
        image = np.asarray(observation[key])
        if image.shape != (256, 256, 3) or image.dtype != np.uint8 or not np.isfinite(image).all():
            raise ValueError(f"Invalid RGB observation {key}: {image.shape}, {image.dtype}")
        images[key] = image_tools.convert_to_uint8(
            image_tools.resize_with_pad(np.ascontiguousarray(image[::-1, ::-1]), 224, 224)
        )
    state = np.concatenate((
        observation["robot0_eef_pos"],
        quaternion_to_axis_angle(observation["robot0_eef_quat"], np),
        observation["robot0_gripper_qpos"],
    ))
    if state.shape != (8,) or not np.isfinite(state).all():
        raise ValueError(f"Invalid proprioception state: {state.shape}")
    return {
        "observation/image": images["agentview_image"],
        "observation/wrist_image": images["robot0_eye_in_hand_image"],
        "observation/state": state,
        "prompt": str(instruction),
    }


def episode(args, task, task_id, init_index, initial_state, initial_state_file, output, client,
            np, image_tools, imageio, OffScreenRenderEnv) -> dict:
    identifier = f"libero-task{task_id}-init{init_index}-seed{args.seed}"
    destination = output / f"{identifier}.json"
    video_path = output / f"{identifier}.mp4"
    started = time.monotonic()
    result = {
        "status": "running",
        "success": None,
        "suite": args.suite,
        "task_id": task_id,
        "task_name": task.name,
        "instruction": task.language,
        "init_index": init_index,
        "seed": args.seed,
        "initial_state_file": str(initial_state_file),
        "initial_state_sha256": hashlib.sha256(np.asarray(initial_state).tobytes()).hexdigest(),
        "server": f"127.0.0.1:{args.port}",
        "stabilization_steps": 10,
        "max_policy_steps": MAX_POLICY_STEPS[args.suite],
        "replan_steps": 5,
        "steps_total": 0,
        "policy_steps": 0,
        "observations_checked": 0,
        "actions_checked": 0,
        "policy_queries": [],
        "video": str(video_path),
        "result_file": str(destination),
    }
    env = None
    frames = []
    terminal_done = False
    try:
        bddl = LIBERO_REPOSITORY / "libero" / "libero" / "bddl_files" / task.problem_folder / task.bddl_file
        env = OffScreenRenderEnv(bddl_file_name=str(bddl), camera_heights=256, camera_widths=256)
        env.seed(args.seed)
        env.reset()
        observation = env.set_init_state(initial_state)
        for _ in range(10):
            observation, _, done, _ = env.step([0.0] * 6 + [-1.0])
            result["steps_total"] += 1
            if done:
                raise ValueError("Task terminated during stabilization, before policy execution")
        action_plan = collections.deque()
        while result["policy_steps"] < MAX_POLICY_STEPS[args.suite]:
            element = policy_input(observation, task.language, np, image_tools)
            result["observations_checked"] += 1
            frames.append(element["observation/image"])
            if not action_plan:
                query_record = {"before_policy_step": result["policy_steps"], "status": "running"}
                result["policy_queries"].append(query_record)
                query_started = time.monotonic()
                try:
                    response = client.infer(element)
                except Exception:
                    query_record["status"] = "error"
                    raise
                finally:
                    query_record["latency_seconds"] = time.monotonic() - query_started
                query_record["status"] = "response_received"
                if not isinstance(response, dict) or "actions" not in response:
                    raise ValueError("Policy response has no actions array")
                chunk = np.asarray(response["actions"])
                if chunk.ndim != 2 or chunk.shape[0] < 5 or chunk.shape[1] != 7:
                    raise ValueError(f"Invalid action chunk shape: {chunk.shape}; expected >=5 x 7")
                if not np.issubdtype(chunk.dtype, np.number) or not np.isfinite(chunk).all():
                    raise ValueError("Policy action chunk contains invalid or nonfinite values")
                query_record.update({
                    "status": "validated",
                    "action_shape": list(chunk.shape),
                    "action_finite": True,
                    "action_minimum": float(chunk.min()),
                    "action_maximum": float(chunk.max()),
                })
                action_plan.extend(chunk[:5])
            action = np.asarray(action_plan.popleft())
            if action.shape != (7,) or not np.isfinite(action).all():
                raise ValueError("Invalid action sent to the simulator")
            result["actions_checked"] += 1
            observation, reward, done, _ = env.step(action.tolist())
            result["policy_steps"] += 1
            result["steps_total"] += 1
            if not np.isfinite(float(reward)):
                raise ValueError("Simulator reward is nonfinite")
            if done:
                terminal_done = True
                break
        # Validate the final observation as well as observations used by the policy.
        policy_input(observation, task.language, np, image_tools)
        result["observations_checked"] += 1
        result["status"] = "completed"
        result["success"] = terminal_done
        result["termination"] = "environment_done" if terminal_done else "policy_step_limit"
    except Exception as exc:
        result["status"] = "error"
        result["success"] = None
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        if env is not None:
            try:
                env.close()
            except Exception as exc:
                result["close_error"] = str(exc)
                result["status"] = "error"
                result["success"] = None
    if frames:
        try:
            imageio.mimwrite(video_path, frames, fps=10)
        except Exception as exc:
            result["video_error"] = str(exc)
            result["status"] = "error"
            result["success"] = None
    else:
        result["video"] = None
    latencies = [item["latency_seconds"] for item in result["policy_queries"]]
    result["policy_query_latency_seconds"] = {
        "count": len(latencies),
        "mean": float(np.mean(latencies)) if latencies else None,
        "median": float(np.median(latencies)) if latencies else None,
        "p95": float(np.percentile(latencies, 95)) if latencies else None,
    }
    result["finite_checks"] = {
        "rgb_dtype": "uint8",
        "rgb_source_shape": [256, 256, 3],
        "rgb_policy_shape": [224, 224, 3],
        "state_shape": [8],
        "action_shape": [7],
        "passed": result["status"] == "completed",
    }
    result["environment_terminal_done_observed"] = terminal_done
    result["elapsed_seconds"] = time.monotonic() - started
    write_json(destination, result)
    return result


def evaluate(args, output: Path, report: dict) -> None:
    benchmark_root = configure_paths(output)
    import numpy as np
    import torch
    import imageio
    from libero.libero import benchmark
    from libero.libero.envs import OffScreenRenderEnv
    from openpi_client import image_tools, msgpack_numpy
    from openpi_client.websocket_client_policy import WebsocketClientPolicy
    from websockets.sync.client import connect

    # Keep the official protocol while replacing its unlimited waiting with
    # bounded waits; an unavailable/failed service is an operational error.
    class BoundedPolicyClient(WebsocketClientPolicy):
        def _wait_for_server(self):
            connection = connect(self._uri, compression=None, max_size=None, open_timeout=30)
            try:
                metadata = msgpack_numpy.unpackb(connection.recv(timeout=30))
            except Exception:
                connection.close()
                raise
            return connection, metadata

        def infer(self, observation):
            self._ws.send(self._packer.pack(observation))
            response = self._ws.recv(timeout=args.query_timeout)
            if isinstance(response, str):
                raise RuntimeError(f"Inference server error: {response}")
            return msgpack_numpy.unpackb(response)

    np.random.seed(args.seed)
    report["packages"] = {
        name: importlib.metadata.version(name)
        for name in ("numpy", "torch", "mujoco", "robosuite", "openpi-client", "websockets", "imageio")
    }
    suite = benchmark.get_benchmark_dict()[args.suite]()
    if args.task_ids == ["all"]:
        task_ids = list(range(suite.n_tasks))
    else:
        task_ids = [int(value) for value in args.task_ids]
        if len(set(task_ids)) != len(task_ids) or not all(0 <= index < suite.n_tasks for index in task_ids):
            raise ValueError("Task IDs must be distinct valid indices, or the single value all")
    report["task_ids"] = task_ids
    report["requested_episodes"] = len(task_ids) * args.trials
    client = BoundedPolicyClient("127.0.0.1", args.port)
    try:
        report["server_metadata_keys"] = list(map(str, client.get_server_metadata().keys()))
        for task_id in task_ids:
            task = suite.get_task(task_id)
            initial_state_file = benchmark_root / "init_files" / task.problem_folder / task.init_states_file
            initial_states = torch.load(initial_state_file, map_location="cpu", weights_only=False)
            if args.trials > len(initial_states):
                raise ValueError(f"Requested {args.trials} trials but task {task_id} has {len(initial_states)} saved initial states")
            for init_index in range(args.trials):
                result = episode(args, task, task_id, init_index, initial_states[init_index], initial_state_file,
                                 output, client, np, image_tools, imageio, OffScreenRenderEnv)
                report["episodes"].append(result)
                if result["status"] == "error":
                    return
    finally:
        client._ws.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=MAX_POLICY_STEPS, default="libero_spatial")
    parser.add_argument("--task-ids", nargs="+", default=["0"], help="Task indices, or all for the whole suite")
    parser.add_argument("--trials", type=int, default=1, help="Trials per task, using initial-state indices 0..trials-1")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--query-timeout", type=float, default=300.0)
    parser.add_argument("--output-dir", type=Path, help="Output directory; default is a new timestamped artifact directory")
    args = parser.parse_args()
    if args.trials < 1 or args.query_timeout <= 0:
        parser.error("trials and query-timeout must be positive")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = (args.output_dir or ARTIFACT_ROOT / f"libero-eval-{timestamp}").expanduser().resolve()
    if args.output_dir is not None and output.exists():
        if not output.is_dir() or any(output.iterdir()):
            parser.error("--output-dir must be a new or empty directory; existing evaluation files will not be overwritten")
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    report = {
        "check": "pi05_libero_closed_loop_evaluation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.executable,
        "suite": args.suite,
        "trials_per_task": args.trials,
        "seed": args.seed,
        "server": f"127.0.0.1:{args.port}",
        "renderer": "egl",
        "replan_steps": 5,
        "episodes": [],
        "output_directory": str(output),
        "source_provenance": source_provenance(),
        "formal_paper_reproduction": False,
    }
    with (output / "libero-console.log").open("w", encoding="utf-8") as console:
        with contextlib.redirect_stdout(console), contextlib.redirect_stderr(console):
            try:
                evaluate(args, output, report)
            except Exception as exc:
                report["error"] = str(exc)
                report["traceback"] = traceback.format_exc()
    completed = [item for item in report["episodes"] if item["status"] == "completed"]
    errors = [item for item in report["episodes"] if item["status"] == "error"]
    report["status"] = "error" if errors or "error" in report else "completed"
    report["completed_episodes"] = len(completed)
    report["error_episodes"] = len(errors)
    report["successful_episodes"] = sum(bool(item["success"]) for item in completed)
    report["success_rate"] = (
        report["successful_episodes"] / len(completed)
        if report["status"] == "completed" and completed else None
    )
    report["elapsed_seconds"] = time.monotonic() - started
    destination = output / "libero-evaluation.json"
    write_json(destination, report)
    print(f"status={report['status']} completed={len(completed)} errors={len(errors)} success_rate={report['success_rate']}")
    print(f"report={destination}")
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

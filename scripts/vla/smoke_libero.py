#!/usr/bin/env python3
"""Check LIBERO reset, fixed initial state, EGL RGB rendering and dummy steps.

No model is loaded and no task-success claim is made. Run with the isolated
pi05-client interpreter. Config and outputs stay beneath the output directory.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace" / "vla_baselines"
LIBERO_REPOSITORY = WORKSPACE / "repos" / "libero"
DEFAULT_OUTPUT = WORKSPACE / "artifacts" / "pi05-2026-10-06" / "libero-smoke"


def quaternion_to_axis_angle(quaternion, np):
    quaternion = np.asarray(quaternion, dtype=np.float64)
    scalar = float(np.clip(quaternion[3], -1.0, 1.0))
    denominator = math.sqrt(max(0.0, 1.0 - scalar * scalar))
    if math.isclose(denominator, 0.0):
        return np.zeros(3, dtype=np.float64)
    return quaternion[:3] * (2.0 * math.acos(scalar) / denominator)


def describe_observation(observation, output: Path, prefix: str, np, Image) -> dict:
    report = {}
    for camera in ("agentview", "robot0_eye_in_hand"):
        image = np.asarray(observation[f"{camera}_image"])
        if image.shape != (256, 256, 3) or image.dtype != np.uint8:
            raise ValueError(f"Unexpected {camera} RGB: {image.shape}, {image.dtype}")
        if not np.isfinite(image).all() or float(image.std()) <= 0:
            raise ValueError(f"Invalid or blank {camera} RGB")
        destination = output / f"libero-{prefix}-{camera}.png"
        # Official openpi preprocessing rotates both cameras by 180 degrees.
        Image.fromarray(np.ascontiguousarray(image[::-1, ::-1])).save(destination)
        report[camera] = {
            "shape": list(image.shape),
            "dtype": str(image.dtype),
            "minimum": int(image.min()),
            "maximum": int(image.max()),
            "std": float(image.std()),
            "frame": str(destination),
            "saved_orientation": "official_openpi_180_degree_rotation",
        }
    state = np.concatenate(
        (
            observation["robot0_eef_pos"],
            quaternion_to_axis_angle(observation["robot0_eef_quat"], np),
            observation["robot0_gripper_qpos"],
        )
    )
    if state.shape != (8,) or not np.isfinite(state).all():
        raise ValueError(f"Invalid pi0.5 proprioception state: shape={state.shape}")
    report["pi05_state"] = {"shape": [8], "values": state.tolist(), "finite": True}
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("libero_spatial", "libero_object", "libero_goal", "libero_10"), default="libero_spatial")
    parser.add_argument("--task-id", type=int, default=0)
    parser.add_argument("--init-index", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--steps", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.steps < 1 or args.steps > 10:
        parser.error("--steps must be between 1 and 10 for this short smoke check")
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    config_directory = output / "libero-config"
    config_directory.mkdir(exist_ok=True)
    unused_datasets = output / "libero-unused-datasets"
    unused_datasets.mkdir(exist_ok=True)
    benchmark_root = LIBERO_REPOSITORY / "libero" / "libero"
    config = {
        "benchmark_root": str(benchmark_root),
        "bddl_files": str(benchmark_root / "bddl_files"),
        "init_states": str(benchmark_root / "init_files"),
        "datasets": str(unused_datasets),
        "assets": str(benchmark_root / "assets"),
    }
    # JSON is a valid YAML subset, avoiding imports before the isolated config exists.
    (config_directory / "config.yaml").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    os.environ["LIBERO_CONFIG_PATH"] = str(config_directory)
    os.environ["MUJOCO_GL"] = "egl"
    os.environ["MPLCONFIGDIR"] = str(output / "libero-matplotlib-cache")
    os.environ["NUMBA_CACHE_DIR"] = str(output / "libero-numba-cache")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(LIBERO_REPOSITORY))
    started = time.monotonic()
    report = {
        "check": "libero_simulator_without_model",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_loaded": False,
        "task_success_evaluated": False,
        "python": sys.executable,
        "renderer": "egl",
        "suite": args.suite,
        "task_id": args.task_id,
        "init_index": args.init_index,
        "seed": args.seed,
        "requested_dummy_steps": args.steps,
        "libero_config": str(config_directory / "config.yaml"),
    }
    env = None
    try:
        import numpy as np
        import torch
        from PIL import Image
        from libero.libero import benchmark, get_libero_path
        from libero.libero.envs import OffScreenRenderEnv

        np.random.seed(args.seed)
        report["packages"] = {
            package: importlib.metadata.version(package)
            for package in ("numpy", "mujoco", "robosuite", "torch", "openpi-client")
        }
        suite = benchmark.get_benchmark_dict()[args.suite]()
        if not 0 <= args.task_id < suite.n_tasks:
            raise ValueError("Task index is outside the selected suite")
        task = suite.get_task(args.task_id)
        initial_state_file = benchmark_root / "init_files" / task.problem_folder / task.init_states_file
        # These are trusted initial-state assets from the pinned official source
        # archive. They contain NumPy arrays, requiring full loading on torch>=2.6.
        initial_states = torch.load(initial_state_file, map_location="cpu", weights_only=False)
        if not 0 <= args.init_index < len(initial_states):
            raise ValueError("Initial-state index is outside the official saved states")
        bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
        report.update({"task_name": task.name, "instruction": task.language, "bddl_file": str(bddl), "initial_state_file": str(initial_state_file), "initial_states_available": len(initial_states)})
        env = OffScreenRenderEnv(bddl_file_name=str(bddl), camera_heights=256, camera_widths=256)
        env.seed(args.seed)
        reset_observation = env.reset()
        report["reset"] = describe_observation(reset_observation, output, "reset", np, Image)
        observation = env.set_init_state(initial_states[args.init_index])
        report["fixed_init"] = describe_observation(observation, output, "fixed-init", np, Image)
        dummy_action = [0.0] * 6 + [-1.0]
        report["action"] = {"shape": [7], "values": dummy_action, "source": "official_LIBERO_dummy_action"}
        report["dummy_steps"] = []
        for step in range(args.steps):
            observation, reward, done, info = env.step(dummy_action)
            report["dummy_steps"].append({"index": step, "reward": float(reward), "done": bool(done)})
        report["after_dummy_steps"] = describe_observation(observation, output, "after-steps", np, Image)
        report["status"] = "passed_simulator_smoke_only"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    finally:
        if env is not None:
            try:
                env.close()
            except Exception as exc:
                report["close_error"] = str(exc)
                report["status"] = "failed"
        report["elapsed_seconds"] = time.monotonic() - started
    destination = output / "libero-smoke.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed_simulator_smoke_only" else 1


if __name__ == "__main__":
    raise SystemExit(main())

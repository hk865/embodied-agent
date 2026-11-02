#!/usr/bin/env python3
"""Load the official converted pi05_libero policy, measure inference, or serve it.

Run with the isolated pi05-server Python. JAX stays on CPU for transforms;
PyTorch performs GPU inference. The pinned upstream source is left unchanged.
"""

from __future__ import annotations

import argparse
from collections import Counter
import dataclasses
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import sys
import time
import traceback
import uuid


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace" / "vla_baselines"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "serve"))
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--compile-mode", choices=("none", "default", "reduce-overhead", "max-autotune"), default="none")
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("--samples must be at least 2 to distinguish warmup")
    checkpoint = args.checkpoint.resolve()
    if not (checkpoint / "model.safetensors").is_file():
        parser.error("checkpoint must contain a converted model.safetensors")

    os.environ["JAX_PLATFORMS"] = "cpu"
    os.environ.setdefault("OPENPI_DATA_HOME", str(WORKSPACE / "cache" / "openpi"))
    os.environ.setdefault("HF_HOME", str(WORKSPACE / "cache" / "huggingface"))
    upstream = WORKSPACE / "repos" / "openpi"
    sys.path[:0] = [str(upstream / "src"), str(upstream / "packages" / "openpi-client" / "src")]
    logging.basicConfig(level=logging.INFO, force=True)
    report = {
        "run_id": uuid.uuid4().hex,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "checkpoint": str(checkpoint),
        "config": "pi05_libero",
        "seed": args.seed,
        "compile_mode": args.compile_mode,
        "denoising_steps": 10,
        "status": "starting",
        "memory_scope": "PyTorch process cumulative peak including model load; not total device usage",
    }
    write_json(args.output, report)
    try:
        conversion_path = checkpoint / "conversion_report.json"
        conversion = json.loads(conversion_path.read_text())
        if conversion["status"] != "passed" or conversion["config_name"] != "pi05_libero":
            raise RuntimeError("A passed pi05_libero conversion audit is required")
        weight_hash = sha256(checkpoint / "model.safetensors")
        if weight_hash != conversion["model_artifact"]["sha256"]:
            raise RuntimeError("The model no longer matches its conversion audit")
        report["conversion_audit"] = {
            "path": str(conversion_path), "sha256": sha256(conversion_path),
            "model_sha256": weight_hash, "source": conversion["official_source"],
        }
        replacement_root = upstream / "src/openpi/models_pytorch/transformers_replace"
        installed_root = Path(importlib.metadata.distribution("transformers").locate_file("transformers"))
        patch_hashes = {}
        for source in replacement_root.rglob("*.py"):
            relative = source.relative_to(replacement_root)
            if sha256(source) != sha256(installed_root / relative):
                raise RuntimeError(f"Transformers patch mismatch: {relative}")
            patch_hashes[str(relative)] = sha256(source)
        if len(patch_hashes) != 5:
            raise RuntimeError("Expected the five pinned Transformers replacements")
        report["transformers_patches"] = patch_hashes
        import numpy as np
        import torch
        from openpi.policies import libero_policy, policy_config
        from openpi.serving.websocket_policy_server import WebsocketPolicyServer
        from openpi.training import config

        np.random.seed(args.seed)
        torch.manual_seed(args.seed)
        torch.set_num_threads(8)
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable in this environment")
        torch.cuda.reset_peak_memory_stats()
        model_config = config.get_config("pi05_libero")
        model_config = dataclasses.replace(
            model_config,
            model=dataclasses.replace(
                model_config.model,
                pytorch_compile_mode=None if args.compile_mode == "none" else args.compile_mode,
            ),
        )
        start = time.monotonic()
        policy = policy_config.create_trained_policy(model_config, checkpoint, pytorch_device="cuda")
        torch.cuda.synchronize()
        dtype_counts = Counter()
        for parameter in policy._model.parameters():
            dtype_counts[str(parameter.dtype)] += parameter.numel()
        report.update({
            "load_seconds": time.monotonic() - start,
            "torch_version": torch.__version__,
            "python": sys.executable,
            "packages": {name: importlib.metadata.version(name) for name in ("transformers", "jax", "jaxlib", "flax", "websockets", "numpy")},
            "cuda_version": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(),
            "compute_capability": list(torch.cuda.get_device_capability()),
            "action_horizon": model_config.model.action_horizon,
            "parameter_count": sum(dtype_counts.values()),
            "parameter_count_scope": "Unique Torch parameters, including the unused expert language output head; not the paper's parameter count",
            "unused_expert_lm_head_parameters": policy._model.paligemma_with_expert.gemma_expert.lm_head.weight.numel(),
            "parameters_by_dtype": dict(dtype_counts),
            "loaded_allocated_mib": torch.cuda.memory_allocated() / 2**20,
            "loaded_reserved_mib": torch.cuda.memory_reserved() / 2**20,
        })

        class MeasuredPolicy:
            metadata = policy.metadata

            def infer(self, obs: dict) -> dict:
                torch.cuda.synchronize()
                start = time.monotonic()
                result = policy.infer(obs)
                torch.cuda.synchronize()
                actions = np.asarray(result["actions"])
                if actions.shape != (model_config.model.action_horizon, 7) or not np.isfinite(actions).all():
                    raise RuntimeError(f"Invalid actions: shape={actions.shape}, finite={np.isfinite(actions).all()}")
                measurement = {
                    "run_id": report["run_id"],
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "wall_ms": (time.monotonic() - start) * 1000,
                    "action_shape": list(actions.shape),
                    "action_min": float(actions.min()),
                    "action_max": float(actions.max()),
                    "peak_allocated_mib": torch.cuda.max_memory_allocated() / 2**20,
                    "peak_reserved_mib": torch.cuda.max_memory_reserved() / 2**20,
                }
                with args.output.with_suffix(".requests.jsonl").open("a") as handle:
                    handle.write(json.dumps(measurement) + "\n")
                return result

        measured = MeasuredPolicy()
        if args.mode == "smoke":
            observation = libero_policy.make_libero_example()
            observation["prompt"] = "pick up the black bowl and place it on the plate"
            samples = []
            for index in range(args.samples):
                start = time.monotonic()
                result = measured.infer(observation)
                samples.append((time.monotonic() - start) * 1000)
                if index == 0:
                    np.savez_compressed(args.output.with_suffix(".actions.npz"), actions=result["actions"])
                logging.info("Inference %s/%s: %.1f ms", index + 1, args.samples, samples[-1])
            report.update({
                "status": "passed",
                "input_kind": "synthetic_observation_not_task_evaluation",
                "action_shape": list(result["actions"].shape),
                "actions_finite": bool(np.isfinite(result["actions"]).all()),
                "latencies_ms": samples,
                "warm_latency_median_ms": float(np.median(samples[1:])),
                "peak_allocated_mib": torch.cuda.max_memory_allocated() / 2**20,
                "peak_reserved_mib": torch.cuda.max_memory_reserved() / 2**20,
            })
            write_json(args.output, report)
            return 0
        report.update({"status": "serving", "host": "127.0.0.1", "port": args.port})
        write_json(args.output, report)
        WebsocketPolicyServer(measured, host="127.0.0.1", port=args.port, metadata=measured.metadata).serve_forever()
    except KeyboardInterrupt:
        report["status"] = "stopped"
        if "torch" in locals() and torch.cuda.is_initialized():
            report["peak_allocated_mib"] = torch.cuda.max_memory_allocated() / 2**20
            report["peak_reserved_mib"] = torch.cuda.max_memory_reserved() / 2**20
        write_json(args.output, report)
        return 0
    except Exception as exc:
        report.update({"status": "error", "error": str(exc), "traceback": traceback.format_exc()})
        write_json(args.output, report)
        logging.exception("pi05 failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

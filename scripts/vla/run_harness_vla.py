#!/usr/bin/env python3
"""Measure or serve RPent's pinned RLinf Pi0.5 model in its isolated environment."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace/vla_baselines"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "serve"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, default=WORKSPACE / "checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--port", type=int, default=8113)
    parser.add_argument("--parent-watch", action="store_true", help="Exit the RPC service when its parent's stdin pipe closes")
    parser.add_argument("--disable-compile", action="store_true", help="Explicit runtime deviation; default keeps upstream compile setting")
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("at least two samples are required")
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error("output already exists; choose a fresh path")
    checkpoint = args.checkpoint.resolve()
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode, "checkpoint": str(checkpoint), "status": "starting",
        "embodiment": "libero", "denoising_steps": 5, "action_chunk": 5,
        "torch_compile": not args.disable_compile,
        "memory_scope": "Torch process allocator; whole-device use is sampled separately",
    }

    def save() -> None:
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    save()
    try:
        manifest_path = WORKSPACE / "artifacts/harness-2026-10-06/weight-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        sources = {}
        for name in ("harness-rlinf", "harness-openpi", "rpent"):
            receipt = WORKSPACE / "repos" / name / ".source-receipt.json"
            sources[name] = json.loads(receipt.read_text())
        report["sources"] = sources
        expected = [item for item in manifest["objects"] if item["group"] == "rlinf_sft" and item["relative_path"] == "model.safetensors"]
        if len(expected) != 1:
            raise RuntimeError("one pinned SFT model manifest entry is required")
        weight = checkpoint / "model.safetensors"
        if weight.stat().st_size != expected[0]["size"]:
            raise RuntimeError("SFT checkpoint size differs from the pinned manifest")
        actual_hash = sha256(weight)
        if actual_hash != expected[0]["sha256"]:
            raise RuntimeError("SFT checkpoint SHA256 differs from the pinned manifest")
        report["checkpoint_sha256"] = actual_hash
        os.environ["JAX_PLATFORMS"] = "cpu"
        os.environ["ROBOT_PLATFORM"] = "LIBERO"
        os.environ.setdefault("OPENPI_DATA_HOME", str(WORKSPACE / "cache/openpi"))
        os.environ.setdefault("HF_HOME", str(WORKSPACE / "cache/huggingface"))
        sys.path[:0] = [str(WORKSPACE / "repos" / name) for name in ("rpent", "harness-rlinf")]
        sys.path.insert(0, str(WORKSPACE / "repos/harness-openpi/src"))
        import numpy as np
        import torch
        from rpent.robots.components.pi05_vla_client import _encode_obs_libero
        from rpent.robots.components.pi05_vla_server import Pi05VLAFacade
        if args.disable_compile:
            # Wrap only the local facade's config builder; the fixed source tree stays intact.
            from rpent.robots.components import pi05_vla_server
            upstream_builder = pi05_vla_server.build_model_cfg

            def runtime_config(*a, **kw):
                cfg = upstream_builder(*a, **kw)
                cfg.openpi.torch_compile = False
                return cfg

            pi05_vla_server.build_model_cfg = runtime_config
        torch.set_num_threads(8)
        torch.manual_seed(0)
        np.random.seed(0)
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")
        torch.cuda.reset_peak_memory_stats()
        started = time.monotonic()
        facade = Pi05VLAFacade(model_path=str(checkpoint), embodiment="libero")
        torch.cuda.synchronize()
        report["load_seconds"] = time.monotonic() - started
        report["parameter_counts_by_dtype"] = dict(Counter({dtype: sum(p.numel() for p in facade._model.parameters() if str(p.dtype) == dtype) for dtype in {str(p.dtype) for p in facade._model.parameters()}}))
        report["packages"] = {name: importlib.metadata.version(name) for name in ("torch", "torchvision", "transformers", "jax", "flax", "numpy", "ray")}
        image = np.zeros((256, 256, 3), dtype=np.uint8)
        image[64:192, 80:176] = [180, 100, 40]
        obs = _encode_obs_libero({"main_images": image, "wrist_images": image.copy(), "states": np.zeros(8, dtype=np.float32), "task_descriptions": "pick up the alphabet soup and place it in the basket"})
        timings = []
        for _ in range(args.samples):
            start = time.monotonic()
            actions = facade.predict(obs, {"mode": "eval"})
            torch.cuda.synchronize()
            timings.append((time.monotonic() - start) * 1000)
            if actions.shape != (1, 5, 7) or not np.isfinite(actions).all():
                raise RuntimeError(f"invalid finite batched action shape: {actions.shape}")
        report.update({"status": "passed", "action_shape": list(actions.shape), "action_dtype": str(actions.dtype), "inference_ms": timings, "warm_median_ms": float(np.median(timings[1:])), "cuda_peak_allocated_mib": torch.cuda.max_memory_allocated() / 2**20, "cuda_peak_reserved_mib": torch.cuda.max_memory_reserved() / 2**20})
        save()
        print(json.dumps({k: report[k] for k in ("status", "action_shape", "warm_median_ms", "cuda_peak_reserved_mib")}), flush=True)
        if args.mode == "serve":
            facade.serve(transport="http", host="127.0.0.1", port=args.port, parent_watch=args.parent_watch)
        return 0
    except Exception as exc:
        report.update({"status": "failed", "error_type": type(exc).__name__, "error": str(exc), "traceback": traceback.format_exc()})
        save()
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

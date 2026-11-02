#!/usr/bin/env python3
"""Test RPent's unchanged SAM3 image facade on a saved LIBERO RGB frame.

This measures local text/point segmentation and memory, not a Harness episode,
semantic accuracy, or robot task success. GPU use must be coordinated with the
other model services before running this script.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace" / "vla_baselines"
SAM3_REPOSITORY = WORKSPACE / "repos" / "harness-sam3"
RPENT_REPOSITORY = WORKSPACE / "repos" / "rpent"
DEFAULT_IMAGE = WORKSPACE / "artifacts" / "pi05-2026-10-06" / "libero-smoke" / "libero-after-steps-agentview.png"
ARTIFACT_ROOT = WORKSPACE / "artifacts" / "harness-2026-10-06"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False, default=str) + "\n")


def nvidia_snapshot() -> dict:
    queries = {
        "gpus": ["nvidia-smi", "--query-gpu=index,uuid,name,memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
        "compute_processes": ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"],
    }
    snapshot = {}
    for name, command in queries.items():
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        snapshot[name] = {"returncode": result.returncode, "output": result.stdout.strip(), "error": result.stderr.strip()}
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--expected-sha256", help="Published checkpoint SHA256, if provided by the weight receipt")
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--phase", choices=("solo", "co-resident"), required=True)
    parser.add_argument("--cuda-device", type=int, default=0)
    parser.add_argument("--point", type=int, nargs=2, metavar=("ROW", "COL"))
    parser.add_argument("--text-prompts", nargs=2, default=("black bowl", "plate"), metavar=("TEXT1", "TEXT2"))
    parser.add_argument("--min-score", type=float, default=0.2)
    args = parser.parse_args()
    checkpoint, image_path = args.checkpoint.resolve(), args.image.resolve()
    if not checkpoint.is_file() or not image_path.is_file():
        parser.error("The completed local checkpoint and saved RGB image must exist.")
    if not 0 <= args.min_score <= 1:
        parser.error("min-score must be between 0 and 1")
    run_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = (args.output_dir or ARTIFACT_ROOT / f"sam3-{args.phase}-{timestamp}").resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("Use a new or empty output directory.")
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "sam3-smoke.json"
    report = {
        "run_id": run_id, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": args.phase, "cuda_visible_device": args.cuda_device,
        "text_prompts": list(args.text_prompts),
        "checkpoint": str(checkpoint), "source_image": str(image_path),
        "status": "starting", "queries": [], "load_state_dict_calls": [],
        "validation_scope": "One real LIBERO frame through RPent SAM3 text and point APIs; no semantic ground truth or full Harness/robot evaluation.",
        "weight_precision_policy": "Unchanged RPent FP32 weights with CUDA BF16 autocast; no model-wide BF16 conversion.",
        "memory_scope": "Torch peaks are this process; global GPU used memory is sampled via CUDA mem_get_info every 0.1 seconds. The phase is operator-selected and baseline processes are recorded.",
    }
    write_json(report_path, report)
    started = time.monotonic()
    torch = None
    monitor_thread = None
    monitor_stop = threading.Event()
    global_memory = []
    exit_code = 1
    try:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(args.cuda_device)
        os.environ.setdefault("HF_HOME", str(WORKSPACE / "cache" / "huggingface"))
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        sys.path[:0] = [str(SAM3_REPOSITORY), str(RPENT_REPOSITORY)]
        sys.dont_write_bytecode = True
        import numpy as np
        from PIL import Image

        with Image.open(image_path) as source:
            rgb = np.asarray(source.convert("RGB"))
        if rgb.ndim != 3 or rgb.shape[-1] != 3 or rgb.dtype != np.uint8:
            raise ValueError(f"Invalid source RGB: {rgb.shape} / {rgb.dtype}")
        height, width = rgb.shape[:2]
        report["source_image_sha256"] = sha256(image_path)
        report["source_image_shape"] = list(rgb.shape)
        report["checkpoint_bytes"] = checkpoint.stat().st_size
        report["checkpoint_sha256"] = sha256(checkpoint)
        if args.expected_sha256 is not None and report["checkpoint_sha256"] != args.expected_sha256:
            raise RuntimeError("The checkpoint does not match its published expected SHA256.")
        report["expected_checkpoint_sha256"] = args.expected_sha256
        weight_receipt = ARTIFACT_ROOT / "weight-verification.json"
        if weight_receipt.is_file():
            report["weight_verification_receipt"] = {"path": str(weight_receipt), "sha256": sha256(weight_receipt), "contents": json.loads(weight_receipt.read_text())}
        shutil.copyfile(image_path, output / "source-frame.png")
        report["sources"] = {}
        for name, repository in (("sam3", SAM3_REPOSITORY), ("rpent", RPENT_REPOSITORY)):
            receipt_path = repository / ".source-receipt.json"
            report["sources"][name] = {"receipt": json.loads(receipt_path.read_text()), "receipt_sha256": sha256(receipt_path)}
        source_paths = [
            SAM3_REPOSITORY / "sam3/model_builder.py",
            SAM3_REPOSITORY / "sam3/model/sam3_image_processor.py",
            SAM3_REPOSITORY / "sam3/model/sam1_task_predictor.py",
            RPENT_REPOSITORY / "rpent/robots/components/sam3_server.py",
        ]
        report["source_file_sha256"] = {str(path): sha256(path) for path in source_paths}
        report["nvidia_before_cuda_initialization"] = nvidia_snapshot()

        import torch as torch_module
        torch = torch_module
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")
        torch.cuda.set_device(0)
        torch.set_num_threads(8)
        torch.manual_seed(0)
        np.random.seed(0)
        report["packages"] = {
            name: importlib.metadata.version(name)
            for name in ("torch", "torchvision", "numpy", "pillow", "einops", "timm", "iopath", "ftfy")
        }
        report["python"] = sys.version
        report["interpreter"] = sys.executable
        report["gpu"] = torch.cuda.get_device_name(0)
        report["compute_capability"] = list(torch.cuda.get_device_capability(0))
        torch.cuda.reset_peak_memory_stats(0)

        def memory_sample():
            free, total = torch.cuda.mem_get_info(0)
            sample = {"elapsed_seconds": time.monotonic() - started, "used_mib": (total - free) / 2**20, "free_mib": free / 2**20, "total_mib": total / 2**20}
            global_memory.append(sample)
            return sample

        def monitor():
            while not monitor_stop.is_set():
                try:
                    memory_sample()
                except Exception as error:
                    report["memory_monitor_error"] = str(error)
                    break
                monitor_stop.wait(0.1)

        report["global_memory_after_cuda_initialization"] = memory_sample()
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

        from rpent.robots.components.sam3_server import Sam3Facade

        original_load = torch.nn.Module.load_state_dict

        def audited_load(model, state_dict, strict=True, assign=False):
            result = original_load(model, state_dict, strict=strict, assign=assign)
            audit = {
                "model_class": type(model).__name__, "strict": strict,
                "source_keys": len(state_dict), "missing_keys": list(result.missing_keys),
                "unexpected_keys": list(result.unexpected_keys),
            }
            report["load_state_dict_calls"].append(audit)
            # Extra checkpoint entries can belong to video-only components;
            # missing model entries would leave randomly initialized weights.
            if result.missing_keys:
                raise RuntimeError(f"SAM3 checkpoint leaves missing model keys: {list(result.missing_keys)}")
            return result

        torch.nn.Module.load_state_dict = audited_load
        load_started = time.monotonic()
        try:
            facade = Sam3Facade(str(checkpoint))
        finally:
            torch.nn.Module.load_state_dict = original_load
        torch.cuda.synchronize(0)
        report["model_load_seconds"] = time.monotonic() - load_started
        if not report["load_state_dict_calls"]:
            raise RuntimeError("No SAM3 checkpoint load was audited.")
        dtype_counts = Counter()
        interactive_parameters = 0
        parameter_bytes = 0
        for name, parameter in facade._model.named_parameters():
            dtype_counts[str(parameter.dtype)] += parameter.numel()
            parameter_bytes += parameter.numel() * parameter.element_size()
            if name.startswith("inst_interactive_predictor."):
                interactive_parameters += parameter.numel()
        report["model_parameter_count"] = sum(dtype_counts.values())
        report["model_parameters_by_dtype"] = dict(dtype_counts)
        report["model_parameter_bytes"] = parameter_bytes
        report["interactive_predictor_parameters"] = interactive_parameters
        report["interactive_predictor_count_scope"] = "Names under inst_interactive_predictor; excludes any additional SAM2 neck in the shared vision backbone."
        report["model_input_resolution"] = facade._processor.resolution
        report["loaded_torch_allocated_mib"] = torch.cuda.memory_allocated(0) / 2**20
        report["loaded_torch_reserved_mib"] = torch.cuda.memory_reserved(0) / 2**20
        report["loaded_global_memory"] = memory_sample()
        if set(dtype_counts) != {"torch.float32"}:
            raise RuntimeError(f"The baseline weights are not uniformly FP32: {dict(dtype_counts)}")
        image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

        def query(label, *, text_prompt=None, point=None):
            entry = {"label": label, "text_prompt": text_prompt, "point_row_col": point, "min_score": args.min_score, "status": "running"}
            report["queries"].append(entry)
            query_started = time.monotonic()
            torch.cuda.synchronize(0)
            try:
                payload = facade.segment(image_base64, text_prompt=text_prompt, point=point, min_score=args.min_score)
                torch.cuda.synchronize(0)
                if payload.get("score") is not None and not math.isfinite(float(payload["score"])):
                    entry["invalid_score_repr"] = repr(payload["score"])
                    raise ValueError("SAM3 returned a nonfinite score")
                if payload.get("box") is not None and not np.isfinite(np.asarray(payload["box"], dtype=float)).all():
                    entry["invalid_box_repr"] = repr(payload["box"])
                    raise ValueError("SAM3 returned a nonfinite box")
                entry.update({key: value for key, value in payload.items() if key != "mask_png_base64"})
                mask = None
                if payload.get("found"):
                    raw = base64.b64decode(payload["mask_png_base64"], validate=True)
                    with Image.open(io.BytesIO(raw)) as source:
                        mask = np.asarray(source.convert("L")) > 0
                    if mask.shape != (height, width) or not mask.any():
                        raise ValueError(f"Invalid returned mask: {mask.shape}")
                    mask_path = output / f"mask-{label}.png"
                    mask_path.write_bytes(raw)
                    entry.update({"mask_path": str(mask_path), "mask_sha256": sha256(mask_path), "mask_pixels": int(mask.sum()), "mask_fraction": float(mask.mean())})
                    if point is not None:
                        entry["mask_contains_prompt_point"] = bool(mask[point[0], point[1]])
                entry["status"] = "completed"
                return mask
            except Exception as error:
                entry.update({"status": "error", "error": str(error)})
                raise
            finally:
                entry["elapsed_seconds"] = time.monotonic() - query_started
                entry["torch_peak_allocated_mib"] = torch.cuda.max_memory_allocated(0) / 2**20
                entry["torch_peak_reserved_mib"] = torch.cuda.max_memory_reserved(0) / 2**20
                entry["global_memory"] = memory_sample()
                write_json(report_path, report)

        labels = ("black-bowl", "plate") if tuple(args.text_prompts) == ("black bowl", "plate") else ("text-1", "text-2")
        first_mask = query(labels[0], text_prompt=args.text_prompts[0])
        second_mask = query(labels[1], text_prompt=args.text_prompts[1])
        if args.point is not None:
            point = list(args.point)
            point_source = "explicit_argument"
        else:
            mask = first_mask if first_mask is not None else second_mask
            if mask is None:
                point = [height // 2, width // 2]
                point_source = "image_center_fallback_no_text_mask"
            else:
                rows, cols = np.nonzero(mask)
                selected = int(np.argmin((rows - rows.mean()) ** 2 + (cols - cols.mean()) ** 2))
                point = [int(rows[selected]), int(cols[selected])]
                selected_label = labels[0] if first_mask is not None else labels[1]
                point_source = f"interior_pixel_of_predicted_{selected_label}_mask"
        if not (0 <= point[0] < height and 0 <= point[1] < width):
            raise ValueError(f"Point is outside the source image: {point}")
        report["point_prompt_selection"] = {"row_col": point, "source": point_source, "ground_truth_validated": False}
        query("positive-point", point=point)
        report["all_queries_returned_nonempty_masks"] = all(entry.get("found") for entry in report["queries"])
        report["status"] = "passed_segmentation_smoke" if report["all_queries_returned_nonempty_masks"] else "completed_with_missing_detections"
        exit_code = 0 if report["status"] == "passed_segmentation_smoke" else 2
    except Exception as error:
        report.update({"status": "error", "error": f"{type(error).__name__}: {error}", "traceback": traceback.format_exc()})
        print(report["error"], file=sys.stderr)
    finally:
        monitor_stop.set()
        if monitor_thread is not None:
            monitor_thread.join(timeout=2)
        if torch is not None and torch.cuda.is_initialized():
            report["torch_peak_allocated_mib"] = torch.cuda.max_memory_allocated(0) / 2**20
            report["torch_peak_reserved_mib"] = torch.cuda.max_memory_reserved(0) / 2**20
        if global_memory:
            report["global_memory_samples"] = global_memory
            report["global_sampled_peak_used_mib"] = max(item["used_mib"] for item in global_memory)
            report["global_sampled_min_free_mib"] = min(item["free_mib"] for item in global_memory)
        report["elapsed_seconds"] = time.monotonic() - started
        report["peak_process_ram_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(report_path, report)
        print(f"SAM3 {report['status']}: {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

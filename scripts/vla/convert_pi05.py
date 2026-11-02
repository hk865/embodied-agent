#!/usr/bin/env python3
"""Convert pi0.5 with the pinned official mapper and audit every loaded key.

Run with the isolated pi05-server interpreter. This wrapper keeps JAX and Torch
on CPU, disables compilation, copies the checkpoint's own normalization assets,
and rejects missing inference weights or unexpected mapping keys. It does not
claim numerical equivalence to the JAX policy or task success.
"""

from __future__ import annotations

import argparse
from collections import Counter
import dataclasses
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time
import traceback


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPOSITORY = ROOT / "workspace" / "vla_baselines" / "repos" / "openpi"
PALIGEMMA_HEAD = "paligemma_with_expert.paligemma.lm_head.weight"
PALIGEMMA_EMBEDDING = "paligemma_with_expert.paligemma.model.language_model.embed_tokens.weight"
EXPERT_HEAD = "paligemma_with_expert.gemma_expert.lm_head.weight"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(repository: Path) -> str | None:
    top_level = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=repository, text=True, capture_output=True, check=False
    )
    if top_level.returncode != 0 or Path(top_level.stdout.strip()).resolve() != repository.resolve():
        return None
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def source_provenance(repository: Path) -> dict:
    receipt_path = repository / ".source-receipt.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
    revision = git_revision(repository)
    return {
        "commit": revision or receipt.get("commit"),
        "method": "git" if revision else receipt.get("method"),
        "git_commit": revision,
        "receipt": receipt,
        "receipt_sha256": sha256(receipt_path) if receipt_path.is_file() else None,
    }


def dtype_summary(tensors) -> dict:
    summary = {}
    for name, tensor in tensors:
        key = str(tensor.dtype)
        bucket = summary.setdefault(key, {"tensors": 0, "elements": 0, "bytes": 0})
        bucket["tensors"] += 1
        bucket["elements"] += tensor.numel()
        bucket["bytes"] += tensor.numel() * tensor.element_size()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--output-path", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument("--config-name", choices=("pi05_libero", "pi05_droid"), default="pi05_libero")
    parser.add_argument("--precision", choices=("bfloat16", "float32"), default="bfloat16")
    args = parser.parse_args()

    repository = args.repository.resolve()
    checkpoint = args.checkpoint_dir.resolve()
    output = args.output_path.resolve()
    converter_path = repository / "examples" / "convert_jax_model_to_pytorch.py"
    assets_source = checkpoint / "assets"
    if not converter_path.is_file() or not (checkpoint / "params").is_dir():
        parser.error("The official converter and a checkpoint root containing params/ are required.")
    # The upstream mapper currently branches on the checkpoint path string.
    if "pi05" not in str(checkpoint):
        parser.error("The official pi0.5 mapper requires 'pi05' in the checkpoint directory path.")
    if not assets_source.is_dir() or not list(assets_source.rglob("norm_stats.json")):
        parser.error("The source checkpoint must include assets/**/norm_stats.json.")
    if output == checkpoint or checkpoint in output.parents or output in checkpoint.parents:
        parser.error("The output must be separate from the original JAX checkpoint.")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error("Use a new or empty output directory; existing artifacts will not be overwritten.")

    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "conversion_report.json"
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "checkpoint": str(checkpoint),
        "output": str(output),
        "repository": str(repository),
        "config_name": args.config_name,
        "precision": args.precision,
        "status": "started",
        "validation_scope": "key coverage, shapes, dtype, CPU placement and artifact integrity; no JAX/Torch numerical comparison",
        "runtime_overrides": {"JAX_PLATFORMS": "cpu", "CUDA_VISIBLE_DEVICES": "", "pytorch_compile_mode": None, "random_seed": 0},
        "load_state_dict_calls": [],
    }
    started = time.monotonic()
    try:
        os.environ["JAX_PLATFORMS"] = "cpu"
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        sys.path[:0] = [str(repository / "src"), str(repository / "packages" / "openpi-client" / "src")]

        import jax
        import numpy as np
        import safetensors
        import torch
        from openpi.models_pytorch import pi0_pytorch
        from openpi.training import config

        np.random.seed(0)
        torch.manual_seed(0)
        report["python"] = sys.version
        report["packages"] = {
            name: importlib.metadata.version(name)
            for name in ("jax", "jaxlib", "flax", "orbax-checkpoint", "torch", "transformers", "safetensors")
        }
        report["jax_devices"] = [str(device) for device in jax.devices()]
        if any(device.platform != "cpu" for device in jax.devices()):
            raise RuntimeError("Conversion must use CPU JAX devices only.")
        source_files = [
            converter_path,
            repository / "src/openpi/models_pytorch/pi0_pytorch.py",
            repository / "src/openpi/models_pytorch/gemma_pytorch.py",
            repository / "src/openpi/models/pi0_config.py",
        ]
        source_files += sorted((repository / "src/openpi/models_pytorch/transformers_replace").rglob("*.py"))
        report["official_source"] = {
            **source_provenance(repository),
            "file_sha256": {str(path.relative_to(repository)): sha256(path) for path in source_files},
        }

        specification = importlib.util.spec_from_file_location("official_openpi_converter", converter_path)
        if specification is None or specification.loader is None:
            raise RuntimeError("Cannot import the official converter.")
        converter = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(converter)
        model_config = dataclasses.replace(config.get_config(args.config_name).model, pytorch_compile_mode=None)
        if not model_config.pi05:
            raise RuntimeError("Expected a pi0.5 configuration.")
        report["model_config"] = dataclasses.asdict(model_config)

        # The mapper intentionally omits the language output heads. PaliGemma's
        # head must share the loaded embedding. The expert's head is unused by
        # openpi's sampling path, which invokes gemma_expert.model directly.
        inference_source = "\n".join(path.read_text() for path in source_files[1:3])
        expert_head_unused = (
            "self.gemma_expert.model.forward(" in inference_source
            and re.search(r"lm_head|self\.gemma_expert\s*\(|self\.gemma_expert\.forward\s*\(", inference_source) is None
        )
        original_load = pi0_pytorch.PI0Pytorch.load_state_dict

        def audited_load(model, state_dict, strict=True, assign=False):
            # Use the official load behavior, then fail before the mapper saves
            # if anything beyond the two documented output heads is absent.
            result = original_load(model, state_dict, strict=strict, assign=assign)
            audit = {
                "strict": strict,
                "assign": assign,
                "source_keys": len(state_dict),
                "missing_keys": list(result.missing_keys),
                "unexpected_keys": list(result.unexpected_keys),
                "allowed_missing": {},
            }
            report["load_state_dict_calls"].append(audit)
            target_state = model.state_dict()
            if PALIGEMMA_HEAD in result.missing_keys and PALIGEMMA_EMBEDDING in state_dict:
                head = target_state[PALIGEMMA_HEAD]
                embedding = target_state[PALIGEMMA_EMBEDDING]
                if head.shape == embedding.shape and head.dtype == embedding.dtype and head.data_ptr() == embedding.data_ptr():
                    audit["allowed_missing"][PALIGEMMA_HEAD] = "Shares the storage of the loaded PaliGemma token embedding."
            if EXPERT_HEAD in result.missing_keys and expert_head_unused:
                audit["allowed_missing"][EXPERT_HEAD] = "Unused language output head: sampling calls gemma_expert.model.forward, never the causal LM head."
            missing_required = sorted(set(result.missing_keys) - set(audit["allowed_missing"]))
            audit["missing_required_keys"] = missing_required
            audit["model_parameter_dtype_after_load"] = dtype_summary(model.named_parameters())
            audit["model_state_dtype_after_load"] = dtype_summary(target_state.items())
            audit["parameter_devices"] = dict(Counter(str(parameter.device) for parameter in model.parameters()))
            if missing_required or result.unexpected_keys:
                raise RuntimeError(f"Untrusted conversion: required missing keys={missing_required}; unexpected keys={list(result.unexpected_keys)}")
            if any(parameter.device.type != "cpu" for parameter in model.parameters()):
                raise RuntimeError("The official conversion unexpectedly placed parameters outside CPU.")
            audit["coverage_passed"] = True
            return result

        pi0_pytorch.PI0Pytorch.load_state_dict = audited_load
        try:
            converter.convert_pi0_checkpoint(str(checkpoint), args.precision, str(output), model_config)
        finally:
            pi0_pytorch.PI0Pytorch.load_state_dict = original_load
        if len(report["load_state_dict_calls"]) != 1:
            raise RuntimeError("Expected exactly one audited checkpoint load.")

        # Upstream currently looks in checkpoint.parent/assets. The checkpoint
        # root actually owns the assets; copy that verified source explicitly.
        assets_destination = output / "assets"
        if assets_destination.exists():
            shutil.rmtree(assets_destination)
        shutil.copytree(assets_source, assets_destination)
        asset_records = {}
        for source in sorted(path for path in assets_source.rglob("*") if path.is_file()):
            relative = source.relative_to(assets_source)
            destination = assets_destination / relative
            digest = sha256(source)
            if sha256(destination) != digest:
                raise RuntimeError(f"Asset hash mismatch: {relative}")
            asset_records[str(relative)] = {"bytes": source.stat().st_size, "sha256": digest}
        report["assets"] = asset_records

        weights = output / "model.safetensors"
        tensor_records = {}
        saved_dtype = {}
        with safetensors.safe_open(str(weights), framework="pt", device="cpu") as saved:
            report["safetensors_metadata"] = saved.metadata()
            for key in saved.keys():
                tensor_slice = saved.get_slice(key)
                shape = tensor_slice.get_shape()
                dtype = tensor_slice.get_dtype()
                elements = math.prod(shape)
                tensor_records[key] = {"shape": shape, "dtype": dtype, "elements": elements}
                bucket = saved_dtype.setdefault(dtype, {"tensors": 0, "elements": 0})
                bucket["tensors"] += 1
                bucket["elements"] += elements
        if args.precision == "bfloat16" and set(saved_dtype) != {"BF16"}:
            raise RuntimeError(f"Unexpected saved dtype: {saved_dtype}")
        if args.precision == "float32" and set(saved_dtype) != {"F32"}:
            raise RuntimeError(f"Unexpected saved dtype: {saved_dtype}")
        report["model_artifact"] = {
            "path": str(weights), "bytes": weights.stat().st_size, "sha256": sha256(weights),
            "saved_dtype_summary": saved_dtype, "tensors": tensor_records,
        }
        report["status"] = "passed"
        return 0
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
        print(report["error"], file=sys.stderr)
        return 1
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        report["peak_process_ram_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        report["peak_process_ram_source"] = "Linux getrusage(RUSAGE_SELF).ru_maxrss in KiB, divided by 1024; includes imports, conversion and checks."
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
        print(f"Conversion audit: {report_path}")


if __name__ == "__main__":
    raise SystemExit(main())

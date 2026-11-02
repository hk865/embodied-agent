#!/usr/bin/env python3
"""Plan or serially run the upstream RPent LIBERO-Pro evaluation matrix.

Default mode is offline: no model construction, credentials, services or network.
Execution requires --execute, an environment-only DEEPSEEK_API_KEY and an explicit
between-episode spending threshold. Empty assets block before paid requests.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace/vla_baselines"
DEFAULT_CONFIG = WORKSPACE / "configs/deepseek-libero-standard.json"
PRO_ROOT = WORKSPACE / "repos/harness-liberopro/liberopro/liberopro"
STANDARD_ROOT = WORKSPACE / "repos/harness-libero/libero/libero"
STANDARD_SUITES = ("libero_spatial", "libero_object", "libero_goal", "libero_10", "libero_90")
CORE_SUITES = tuple(f"libero_{base}_{kind}" for base in ("spatial", "object", "goal", "10") for kind in ("task", "swap"))


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def task_names(root: Path = PRO_ROOT) -> dict[str, list[str]]:
    """Read the pinned task map without importing Torch or simulator modules."""
    tree = ast.parse((root / "benchmark/libero_suite_task_map.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "libero_task_map" for t in node.targets):
            mapping = ast.literal_eval(node.value)
            return {**{suite: mapping[suite] for suite in STANDARD_SUITES}, **{suite: mapping[suite.rsplit("_", 1)[0]] for suite in CORE_SUITES}}
    raise ValueError("pinned task map assignment is missing")


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text())
    if config["planner"] != "api" or config["model"] != "deepseek:deepseek-flash" or config["base_url"] != "https://api.deepseek.com":
        raise ValueError("only the reviewed official DeepSeek Flash provider is supported")
    if not config.get("images") or config.get("reset_during_evaluation"):
        raise ValueError("this evaluation requires images and forbids reset")
    if config.get("memory_access") != "read_only":
        raise ValueError("evaluation memory must be read-only")
    for key in ("suites", "task_ids", "seeds"):
        if not config[key] or len(config[key]) != len(set(config[key])):
            raise ValueError(f"{key} must be nonempty and unique")
    variant = config.get("libero_type")
    allowed = CORE_SUITES if variant == "pro" else STANDARD_SUITES if variant == "standard" else ()
    if any(s not in allowed for s in config["suites"]):
        raise ValueError("suite does not match the reviewed LIBERO variant")
    for suite in config["suites"]:
        ids = config.get("task_ids_by_suite", {}).get(suite, config["task_ids"])
        if not ids or len(ids) != len(set(ids)) or any(type(t) is not int or not 0 <= t < (90 if suite == "libero_90" else 10) for t in ids):
            raise ValueError("task IDs must be unique and in the suite range")
    if any(type(s) is not int or s < 0 for s in config["seeds"]):
        raise ValueError("seeds must be nonnegative integers")
    for key in ("max_episode_steps", "max_turns", "max_tokens", "planner_timeout_s", "long_planner_timeout_s"):
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(f"{key} must be a positive integer")
    return config


def make_plan(config: dict, only_cells: list[str] | None = None, root: Path | None = None) -> dict:
    root = root or (PRO_ROOT if config["libero_type"] == "pro" else STANDARD_ROOT)
    names = task_names(root)
    # Import only our standard-library shape reader; never use unrestricted torch.load.
    from init_state_shape import initial_state_shape

    selected = set(only_cells or [])
    cells, assets = [], {}
    for suite in config["suites"]:
        for task in config.get("task_ids_by_suite", {}).get(suite, config["task_ids"]):
            name = names[suite][task]
            asset = root / "init_files" / suite / f"{name}.pruned_init"
            bddl = root / "bddl_files" / suite / f"{name}.bddl"
            asset_key = f"{suite}:t{task}"
            for seed in config["seeds"]:
                cell_id = f"{suite}:{task}:{seed}"
                if selected and cell_id not in selected:
                    continue
                if asset_key not in assets:
                    record = {"suite": suite, "task": task, "name": name, "initial_states": str(asset), "bddl": str(bddl)}
                    try:
                        shape = initial_state_shape(asset)
                        if not bddl.is_file():
                            raise ValueError("BDDL file is missing")
                        if not shape or shape[0] <= 0:
                            raise ValueError(f"initial-state array is empty: {shape}")
                        if max(config["seeds"]) >= shape[0]:
                            raise ValueError("configured seeds would repeat saved initial states")
                        record.update(shape=list(shape), init_count=shape[0], sha256=hashlib.sha256(asset.read_bytes()).hexdigest(), bddl_sha256=hashlib.sha256(bddl.read_bytes()).hexdigest(), status="available")
                    except (OSError, ValueError) as exc:
                        record.update(status="blocked", error=str(exc))
                    assets[asset_key] = record
                info = assets[asset_key]
                cells.append({"id": cell_id, "suite": suite, "task": task, "seed": seed,
                              "init_index": seed % info["init_count"] if info["status"] == "available" else None,
                              "status": info["status"], "asset_key": asset_key})
    unknown = selected - {cell["id"] for cell in cells}
    if unknown:
        raise ValueError(f"selected cells are outside the configured matrix: {sorted(unknown)}")
    blocked = [c for c in cells if c["status"] == "blocked"]
    return {"config": config, "selected_episodes": len(cells), "full_config_episodes": sum(len(config.get("task_ids_by_suite", {}).get(s, config["task_ids"])) for s in config["suites"]) * len(config["seeds"]),
            "complete_matrix_selected": not bool(selected), "blocked_episodes": len(blocked), "assets": assets, "cells": cells,
            "preflight": "blocked" if blocked else "asset_headers_available",
            "limits": ["Asset headers do not verify simulator construction or numerical integrity.", "No API, GPU or task-success checks have run in plan mode."]}


def episode_command(config: dict, cell: dict, destination: Path, shared: dict[str, str], max_cost_usd: float = 2.0) -> list[str]:
    timeout = config["long_planner_timeout_s"] if cell["suite"] == "libero_10" or cell["suite"].startswith("libero_10_") else config["planner_timeout_s"]
    command = [str(WORKSPACE / ".venvs/harness-rpent/bin/python"), str(ROOT / "scripts/vla/run_harness.py"),
               "--output-dir", str(destination), "--suite", cell["suite"], "--task", str(cell["task"]), "--seed", str(cell["seed"]),
               "--libero-type", config["libero_type"],
               "--planner", "api", "--model", config["model"], "--base-url", config["base_url"],
               "--reasoning-effort", config["reasoning_effort"], "--max-turns", str(config["max_turns"]),
               "--max-tokens", str(config["max_tokens"]), "--max-episode-steps", str(config["max_episode_steps"]),
               "--planner-timeout-s", str(timeout), "--max-cost-usd", str(max_cost_usd)]
    for name, endpoint in shared.items():
        command += [f"--{name}-endpoint", endpoint]
    return command


def usage_cost(stats: dict, config: dict) -> float:
    rates = config["peak_usd_per_million_tokens"]
    total = max(0, stats.get("total_input_tokens", 0))
    hit = min(total, max(0, stats.get("total_cached_input_tokens", 0)))
    output = max(0, stats.get("total_output_tokens", 0))
    return ((total - hit) * rates["input_cache_miss"] + hit * rates["input_cache_hit"] + output * rates["output"]) / 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--only-cell", action="append", help="Explicit pilot subset: suite:task:seed; repeatable")
    parser.add_argument("--plan-output", type=Path, help="Save an offline plan; refuses existing paths")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--resume", action="store_true", help="Skip recorded episodes; never retry failures silently")
    parser.add_argument("--max-cost-usd", type=float, help="Peak-price threshold checked BETWEEN episodes; not a hard billing cap")
    parser.add_argument("--episode-max-cost-usd", type=float, default=2.0, help="Conservative request reservation limit per episode")
    parser.add_argument("--vla-endpoint", help="Optional warm local service; caller owns its lifecycle")
    parser.add_argument("--sam3-endpoint", help="Optional warm local service; caller owns its lifecycle")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        plan = make_plan(config, args.only_cell)
    except (OSError, ValueError, KeyError, SyntaxError) as exc:
        parser.error(str(exc))
    digest = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    plan["plan_sha256"] = digest
    if args.plan_output:
        args.plan_output.parent.mkdir(parents=True, exist_ok=True)
        with args.plan_output.open("x") as handle:
            json.dump(plan, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    concise = {k: plan[k] for k in ("selected_episodes", "full_config_episodes", "complete_matrix_selected", "blocked_episodes", "preflight", "plan_sha256")}
    concise["blocked_assets"] = [v for v in plan["assets"].values() if v["status"] == "blocked"]
    print(json.dumps(concise, ensure_ascii=False, indent=2), flush=True)
    if not args.execute:
        return 0
    if plan["blocked_episodes"]:
        parser.error("selected matrix has blocked assets; no services or API requests were started")
    if not args.output_dir or args.max_cost_usd is None or not math.isfinite(args.max_cost_usd) or args.max_cost_usd <= 0:
        parser.error("execution requires --output-dir and positive --max-cost-usd (between-episode threshold)")
    if not math.isfinite(args.episode_max_cost_usd) or args.episode_max_cost_usd <= 0:
        parser.error("--episode-max-cost-usd must be positive and finite")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        parser.error("DEEPSEEK_API_KEY is absent; no credential file is read")
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.free", "--format=csv,noheader"], capture_output=True, text=True)
    if gpu.returncode:
        parser.error("NVIDIA driver/GPU is unavailable; no model services or API requests were started")
    output = args.output_dir.resolve()
    if args.resume:
        saved = json.loads((output / "plan.json").read_text())
        if saved["plan_sha256"] != digest:
            parser.error("resume requires identical configuration, selection and asset hashes")
    else:
        output.mkdir(parents=True, exist_ok=False)
        write_json(output / "plan.json", plan)
    shared = {name: endpoint for name, endpoint in (("vla", args.vla_endpoint), ("sam3", args.sam3_endpoint)) if endpoint}
    summary = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "status": "running", "plan_sha256": digest,
               "selected_episodes": len(plan["cells"]), "complete_matrix_selected": plan["complete_matrix_selected"], "results": [],
               "estimated_peak_usd": 0.0, "max_cost_usd_between_episodes": args.max_cost_usd, "cost_warning": config["cost_warning"],
               "service_mode": "caller-owned warm services" if len(shared) == 2 else "unshared services restart per episode"}
    for cell in plan["cells"]:
        destination = output / cell["id"].replace(":", "_")
        result_path = destination / "run-summary.json"
        if args.resume and result_path.is_file():
            result = json.loads(result_path.read_text())
        else:
            if summary["estimated_peak_usd"] >= args.max_cost_usd:
                summary["status"] = "budget_threshold_reached"
                break
            if destination.exists():
                summary.update(status="incomplete_episode_requires_inspection", pending_cell=cell["id"])
                break
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            allowance = min(args.episode_max_cost_usd, args.max_cost_usd - summary["estimated_peak_usd"])
            completed = subprocess.run(episode_command(config, cell, destination, shared, allowance), cwd=ROOT, env=environment)
            result = json.loads(result_path.read_text()) if result_path.is_file() else {"status": "launcher_failed", "exit_code": completed.returncode}
        stats = result.get("planner_stats") or {}
        summary["estimated_peak_usd"] += usage_cost(stats, config)
        summary["results"].append({"cell": cell["id"], "status": result["status"], "native_success": result.get("environment_success"), "planner_stats": stats, "run_summary": str(result_path)})
        write_json(output / "benchmark-summary.json", summary)
        if result["status"] not in ("passed", "task_unsuccessful"):
            summary.update(status="stopped_on_execution_error", pending_cell=cell["id"])
            break
        if not all(type(stats.get(key)) is int and stats[key] >= 0 for key in ("total_input_tokens", "total_output_tokens")):
            summary.update(status="stopped_on_missing_usage", pending_cell=cell["id"])
            break
    if len(summary["results"]) == len(plan["cells"]) and summary["status"] == "running":
        summary["status"] = "completed"
    counts = Counter(result["status"] for result in summary["results"])
    summary.update(completed_episodes=len(summary["results"]), counts=dict(counts), successes=sum(r["native_success"] is True for r in summary["results"]))
    summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(output / "benchmark-summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2), flush=True)
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

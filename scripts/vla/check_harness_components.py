#!/usr/bin/env python3
"""Reuse RPent's GPU E2E component assertions against isolated local services."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace/vla_baselines"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-endpoint", required=True)
    parser.add_argument("--vla-endpoint", required=True)
    parser.add_argument("--sam3-endpoint", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--suite", default="libero_object_swap")
    parser.add_argument("--task", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--libero-type", choices=("standard", "pro"), default="pro")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(WORKSPACE / "repos/rpent"))
    from robots.libero.robot_spec import get_robot_spec
    from tests.e2e_tests.common import parse_runtime_args
    from tests.e2e_tests.libero.scenario import (
        _capture_environment, _environment_action, _pi05_checks, _sam3_check,
    )
    runtime_args = parse_runtime_args(get_robot_spec(), [
        "--suite", args.suite, "--task", str(args.task), "--seed", str(args.seed),
        "--max-episode-steps", "10000", "--libero-type", args.libero_type, "--cuda-device", "0",
        "--env-endpoint", args.env_endpoint,
        "--vla-endpoint", args.vla_endpoint,
        "--sam3-endpoint", args.sam3_endpoint,
    ])
    report = {"scope": "upstream GPU E2E component assertions via explicit remote endpoints; not the full CI installer or online planner", "checks": {}, "status": "starting"}
    try:
        _, report["checks"]["environment"] = _capture_environment(output, runtime_args)
        report["checks"]["environment_action"] = _environment_action(output, runtime_args)
        _, report["checks"]["pi05"] = _pi05_checks(output, runtime_args)
        report["checks"]["sam3"] = _sam3_check(output, runtime_args)
        # Exercise the policy after the segmentation process has retained its image cache.
        _, report["checks"]["pi05_after_sam3"] = _pi05_checks(output / "after-sam3", runtime_args)
        report["status"] = "passed"
        return 0
    except Exception as exc:
        report.update({"status": "failed", "error_type": type(exc).__name__, "error": str(exc), "traceback": traceback.format_exc()})
        traceback.print_exc()
        return 1
    finally:
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())

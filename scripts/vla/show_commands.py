#!/usr/bin/env python3
"""Preview official OpenVLA/pi0.5 LIBERO commands without executing them.

The command fields match the pinned upstream evaluation and policy-server
entry points. Printing a command is not a dependency or deployment check.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import shutil
import sys


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace" / "vla_baselines"
PLAN = WORKSPACE / "experiment_plan.json"
SUITES = {
    "spatial": "libero_spatial",
    "object": "libero_object",
    "goal": "libero_goal",
    "10": "libero_10",
}
MODELS = ("openvla", "pi05-server", "pi05-client")
PRECISIONS = ("4bit", "8bit", "bf16")


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("trials must be at least 1")
    return number


def interpreter_available(interpreter: str) -> bool:
    if "/" in interpreter:
        return Path(interpreter).expanduser().is_file()
    return shutil.which(interpreter) is not None


def build_command(args: argparse.Namespace, baseline: dict) -> tuple[Path, dict, list[str], Path, str]:
    suite = SUITES[args.suite]
    log_directory = WORKSPACE / "logs" / f"{args.model}-{suite}-seed{args.seed}"
    interpreter = args.interpreter or str(WORKSPACE / ".venvs" / args.model / "bin" / "python")
    if interpreter.startswith("~"):
        interpreter = str(Path(interpreter).expanduser())
    env = {"HF_HOME": str(WORKSPACE / "cache"), "MUJOCO_GL": "egl"}

    if args.model == "openvla":
        repository = WORKSPACE / "repos" / "openvla"
        libero = WORKSPACE / "repos" / "libero"
        env["PYTHONPATH"] = ":".join(map(str, (repository, libero)))
        checkpoint = args.checkpoint or baseline["openvla_checkpoints"][suite]
        precision = args.precision or str(baseline["openvla_local_precision_candidate"]).split(";", 1)[0].strip()
        if precision not in PRECISIONS:
            raise ValueError(f"Unsupported default OpenVLA precision in {PLAN}: {precision}")
        command = [
            interpreter, "experiments/robot/libero/run_libero_eval.py",
            "--model_family", "openvla",
            "--pretrained_checkpoint", checkpoint,
            "--task_suite_name", suite,
            "--num_trials_per_task", str(args.trials),
            "--seed", str(args.seed),
            "--center_crop", "True",
            "--use_wandb", "False",
            "--load_in_4bit", str(precision == "4bit"),
            "--load_in_8bit", str(precision == "8bit"),
            "--local_log_dir", str(log_directory),
        ]
        note = (
            f"OpenVLA precision: {precision}. "
            "4bit/8bit runs are adapted local baselines; bf16 is not an acceptance claim."
        )
    else:
        repository = WORKSPACE / "repos" / "openpi"
        libero = WORKSPACE / "repos" / "libero"
        env["PYTHONPATH"] = ":".join(
            map(str, (repository, repository / "src", repository / "packages" / "openpi-client" / "src", libero))
        )
        if args.model == "pi05-server":
            env["OPENPI_DATA_HOME"] = str(WORKSPACE / "cache" / "openpi")
            env["XLA_PYTHON_CLIENT_PREALLOCATE"] = "false"
            command = [
                interpreter, "scripts/serve_policy.py",
                "--env", "LIBERO",
                "--port", "8000",
                "policy:checkpoint",
                "--policy.config", baseline["pi05_config"],
                "--policy.dir", args.checkpoint or baseline["pi05_checkpoint"],
            ]
            note = (
                "Start this service before the pi05-client command. The upstream server binds 0.0.0.0:8000. "
                "Suite/trials/seed label the planned client run; the server has no matching CLI fields."
            )
        else:
            command = [
                interpreter, "examples/libero/main.py",
                "--args.host", "127.0.0.1",
                "--args.port", "8000",
                "--args.task-suite-name", suite,
                "--args.num-trials-per-task", str(args.trials),
                "--args.seed", str(args.seed),
                "--args.replan-steps", str(baseline["pi05_execution_replan_steps"]),
                "--args.video-out-path", str(WORKSPACE / "videos" / f"{args.model}-{suite}-seed{args.seed}"),
            ]
            note = "Requires the matching pi05_libero service at 127.0.0.1:8000. Weights are selected on the server."
    return repository, env, command, log_directory, note


def main() -> int:
    try:
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        baseline = plan["baseline"]
    except (OSError, ValueError, KeyError) as exc:
        print(f"Cannot read experiment plan: {exc}", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--suite", choices=SUITES, default="spatial", help="LIBERO suite, default: spatial")
    parser.add_argument("--trials", type=positive_int, default=baseline["development_trials_per_task"], help="Trials per task; default from the development plan")
    parser.add_argument("--seed", type=int, default=baseline["development_seed"], help="Development seed; default from the plan")
    parser.add_argument("--python", dest="interpreter", help="Override the isolated environment's interpreter")
    parser.add_argument("--checkpoint", help="Override OpenVLA HF/local weights or pi05-server GCS/local weights")
    parser.add_argument("--precision", choices=PRECISIONS, help="OpenVLA only; default from the local precision plan")
    args = parser.parse_args()
    if args.precision and args.model != "openvla":
        parser.error("--precision is only available for OpenVLA")
    if args.checkpoint and args.model == "pi05-client":
        parser.error("pi05-client does not load weights; use --checkpoint with pi05-server")

    try:
        repository, env, command, log_directory, note = build_command(args, baseline)
    except (KeyError, ValueError) as exc:
        print(f"Cannot build command from experiment plan: {exc}", file=sys.stderr)
        return 1

    print("# Command preview only: no execution, package installation, or weight download occurred.")
    print("# Dependencies, GPU compatibility, weights, rendering, and rollout behavior are not accepted yet.")
    if not interpreter_available(command[0]):
        print(f"# Interpreter does not exist or is not on PATH: {command[0]}")
        print("# Prepare this isolated environment before executing the command.")
    if not repository.is_dir():
        print(f"# Source directory is missing: {repository}")
    print(f"# {note}")
    print("cd " + shlex.quote(str(repository)))
    print(shlex.join(["mkdir", "-p", str(log_directory)]))
    invocation = ["env", *(f"{key}={value}" for key, value in env.items()), *command]
    print(shlex.join(invocation) + " > " + shlex.quote(str(log_directory / "console.log")) + " 2>&1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

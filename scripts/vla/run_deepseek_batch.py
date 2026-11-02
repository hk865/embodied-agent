#!/usr/bin/env python3
"""Resume a fixed serial LIBERO matrix under one existing API budget ledger.

The default invocation is an offline plan. Execution never reads credential
files, changes the ledger cap, retries an episode, or changes task strategy.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace/vla_baselines"
SUITES = ("libero_spatial", "libero_object", "libero_goal", "libero_10")
RESERVATION = Decimal("0.3265728")
CONFIGURATION_VERSION = "v2-output-10000"
LEGACY_CONFIGURATION_VERSION = "v1-output-8192"
UPGRADED_CONFIGURATION_VERSION = "v3-output-32000"
VERSION_LIMITS = {LEGACY_CONFIGURATION_VERSION: 8192, "v2-output-10000": 10000, UPGRADED_CONFIGURATION_VERSION: 32000}
CONDITIONAL_UPGRADE_ENABLED = False
UPGRADE_RULE = {"enabled": True, "from_max_tokens": 10000, "to_max_tokens": 32000, "once": True,
                "trigger": "non-success v2 episode with explicit Model token limit (10000) exceeded planner error"}
DEFAULT_LEDGER = WORKSPACE / "artifacts/deepseek-pilot-2026-11-01-budget.json"
DEFAULT_PILOT = WORKSPACE / "artifacts/deepseek-pilot-2026-11-01-libero-spatial-t0-s0"
PROFILE = {"libero_type": "standard", "planner": "api", "model": "deepseek:deepseek-flash", "base_url": "https://api.deepseek.com",
           "reasoning_effort": "high", "max_turns": 100, "max_tokens": 10000, "planner_timeout_s": 1200,
           "max_episode_steps": 10000, "torch_compile": True,
           "memory_revision": "7db66088d06d04ae097682332a09704f13e6fc0c", "memory_version": "GPT_5.5_xhigh",
           "policy": "RLinf/RLinf-Pi05-LIBERO-130-fullshot-SFT@6222623f635769bfc73c9472e29fab9b7fd8e027"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def append_event(path: Path, value: dict):
    with path.open("a") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def matrix() -> list[dict]:
    return [{"id": f"{suite}:t{task}:s{seed}", "suite": suite, "task": task, "seed": seed, "phase": "coverage" if seed == 0 else "full"}
            for seed in range(50) for suite in SUITES for task in range(10)]


def frozen_config(ledger: Path, pilot: Path, *, max_tokens: int = 10000, conditional_upgrade: bool = False) -> dict:
    if max_tokens not in (10000, 32000) or (max_tokens == 32000 and not conditional_upgrade):
        raise ValueError("32000 is permitted only under the conditional upgrade rule")
    paths = [ROOT / "scripts/vla/run_harness.py", ROOT / "scripts/vla/run_deepseek_batch.py",
             ROOT / "scripts/harness/deepseek_api.py", ROOT / "scripts/harness/smoke_environment.py", ROOT / "scripts/harness/shared_model_services.py",
             WORKSPACE / "configs/harness.sources.lock.json"]
    paths += [WORKSPACE / "repos" / name / ".source-receipt.json" for name in ("rpent", "harness-rlinf", "harness-openpi", "harness-libero")]
    config = {"schema_version": 1, "configuration_version": "v2-output-10000" if max_tokens == 10000 else UPGRADED_CONFIGURATION_VERSION,
            "profile": {**PROFILE, "max_tokens": max_tokens}, "suites": list(SUITES), "task_ids": list(range(10)), "seeds": list(range(50)),
            "episodes": 2000, "coverage_episodes": 40, "budget_ledger": str(ledger.resolve()), "cost_limit_usd": "40",
            "pilot": str(pilot.resolve()), "fingerprints": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    if conditional_upgrade:
        config["conditional_output_upgrade"] = dict(UPGRADE_RULE)
    return config


def activate_configuration(config: dict) -> None:
    """Apply the already-validated active profile to subsequent episode commands."""
    global CONFIGURATION_VERSION, RESERVATION, CONDITIONAL_UPGRADE_ENABLED
    maximum = config["profile"]["max_tokens"]
    if maximum not in (10000, 32000) or VERSION_LIMITS[config["configuration_version"]] != maximum:
        raise ValueError("invalid active output configuration")
    PROFILE["max_tokens"] = maximum
    CONFIGURATION_VERSION = config["configuration_version"]
    CONDITIONAL_UPGRADE_ENABLED = config.get("conditional_output_upgrade") == UPGRADE_RULE
    RESERVATION = (Decimal(1_048_576) * Decimal("0.30") + Decimal(maximum) * Decimal("1.20")) / Decimal(1_000_000)


def config_for_resume(output: Path, ledger: Path, pilot: Path) -> dict:
    stored = json.loads((output / "config.json").read_text())
    return frozen_config(ledger, pilot, max_tokens=stored["profile"]["max_tokens"],
                         conditional_upgrade=bool(stored.get("conditional_output_upgrade")))


def digest(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def budget_snapshot(path: Path) -> dict:
    # Atomic writer in the provider means a plain read is always one generation.
    data = json.loads(path.read_text())
    if Decimal(data["limit_usd"]) != Decimal("40"):
        raise ValueError("shared ledger must already have the user-authorized USD40 cap")
    accounted = Decimal(data["accounted_upper_bound_usd"])
    if not accounted.is_finite() or not 0 <= accounted <= Decimal("40"):
        raise ValueError("shared ledger has invalid accounted cost")
    return {key: data.get(key) for key in ("limit_usd", "accounted_upper_bound_usd", "settled_peak_usd", "unsettled_reservations_usd", "request_attempts", "models")}


def can_start(budget: dict) -> bool:
    return Decimal(budget["limit_usd"]) - Decimal(budget["accounted_upper_bound_usd"]) >= RESERVATION


def _flag(command: list, name: str):
    try:
        return command[command.index(name) + 1]
    except (ValueError, IndexError):
        return None


def validate_pilot(path: Path) -> dict:
    report = json.loads((path / "run-summary.json").read_text())
    expected = {"libero_type": "standard", "suite": "libero_spatial", "task": 0, "seed": 0, "max_episode_steps": 10000}
    if report.get("task") != expected or any(report.get(k) != PROFILE[k] for k in ("planner", "model", "base_url", "reasoning_effort", "torch_compile")):
        raise ValueError("pilot runtime profile does not match the fixed matrix")
    command = report.get("commands", {}).get("online_planner", [])
    for flag, expected_value in (("--max-turns", "100"), ("--max-tokens", "8192"), ("--planner-timeout-s", "1200")):
        if _flag(command, flag) != expected_value:
            raise ValueError("pilot model budgets differ from the matrix")
    expected_memory = str(WORKSPACE / "cache/harness-assets-download/memory" / PROFILE["memory_revision"] / PROFILE["memory_version"])
    recorded_memory = Path(_flag(command, "--memory-dir") or "")
    if not recorded_memory.is_absolute():
        recorded_memory = ROOT / recorded_memory
    if recorded_memory.resolve() != Path(expected_memory).resolve() or _flag(command, "--memory-profile") != "local":
        raise ValueError("pilot frozen memory differs from the matrix")
    result = read_result(matrix()[0], path)
    if result["outcome"] != "success":
        raise ValueError("pilot lacks a valid native success trace")
    result.update(imported_pilot=True, configuration_version=LEGACY_CONFIGURATION_VERSION, max_tokens=8192,
                  note="Historical8192-token pilot retained as v1; never pooled silently with the later10000-token configuration. No new request or reset.")
    return result


def read_result(cell: dict, destination: Path, interrupted: bool = False) -> dict:
    path = destination / "run-summary.json"
    report = json.loads(path.read_text()) if path.is_file() else {}
    steps_path = destination / "online-task/states.json"
    valid = False
    steps = []
    if steps_path.is_file():
        try:
            steps = json.loads(steps_path.read_text())["steps"]
            valid = bool(steps) and all(type(s.get("terminated")) is bool and type(s.get("truncated")) is bool for s in steps)
        except (KeyError, TypeError, ValueError):
            pass
    identity = report.get("task") or {}
    valid = valid and all(identity.get(k) == cell[k] for k in ("suite", "task", "seed")) and identity.get("libero_type") == "standard"
    native = any(s["terminated"] for s in steps) if valid else None
    error = str(report.get("planner_error") or report.get("error") or "")
    budget_stopped = "cost cap reached before HTTP send" in error
    timed_out = "timed out" in error.lower() or report.get("error_type") == "TimeoutExpired"
    terminal = report.get("stage") == "online_task_complete" or report.get("status") in ("passed", "task_unsuccessful", "planner_error")
    if native:
        outcome = "success"
    elif budget_stopped:
        outcome = "budget_stopped"
    elif interrupted and not terminal:
        outcome = "interrupted"
    elif valid and (terminal or timed_out):
        outcome = "failure"
    else:
        outcome = "error"
    systemic = outcome == "error" or (bool(error) and not timed_out and not budget_stopped and not native)
    maximum = report.get("max_tokens") or _flag(report.get("commands", {}).get("online_planner", []), "--max-tokens")
    maximum = int(maximum) if maximum is not None else PROFILE["max_tokens"]
    version = report.get("configuration_version") or next((v for v, n in VERSION_LIMITS.items() if n == maximum), CONFIGURATION_VERSION)
    return {**cell, "configuration_version": version, "max_tokens": maximum, "outcome": outcome, "native_success": native, "native_trace_valid": valid, "run_status": report.get("status"),
            "run_summary": str(path), "states": str(steps_path), "planner_elapsed_s": report.get("elapsed_s"),
            "planner_stats": report.get("planner_stats") or {}, "budget_stopped": budget_stopped,
            "timed_out": timed_out, "systemic_error": systemic, "reported_at_utc": now()}


def episode_command(cell: dict, output: Path, ledger: Path, endpoints: dict) -> list[str]:
    command = [str(WORKSPACE / ".venvs/harness-rpent/bin/python"), "-B", str(ROOT / "scripts/vla/run_harness.py"),
               "--output-dir", str(output), "--libero-type", "standard", "--suite", cell["suite"], "--task", str(cell["task"]), "--seed", str(cell["seed"]),
               "--planner", "api", "--model", PROFILE["model"], "--base-url", PROFILE["base_url"], "--reasoning-effort", "high",
               "--max-turns", "100", "--max-tokens", str(PROFILE["max_tokens"]), "--configuration-version", CONFIGURATION_VERSION, "--planner-timeout-s", "1200", "--max-episode-steps", "10000",
               "--max-cost-usd", "40", "--budget-ledger", str(ledger), "--skip-component-checks"]
    for name, endpoint in endpoints.items():
        command += [f"--{name}-endpoint", endpoint]
    return command


def load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    lines = path.read_bytes().splitlines(keepends=True)
    valid_bytes = 0
    for index, line in enumerate(lines):
        try:
            events.append(json.loads(line))
            valid_bytes += len(line)
        except ValueError:
            if index != len(lines) - 1:
                raise ValueError("corrupt interior batch event") from None
            # A killed append can leave only the last line partial. Its episode
            # is reconciled from the earlier durable started event on resume.
            with path.open("r+b") as handle:
                handle.truncate(valid_bytes)
                handle.flush()
                os.fsync(handle.fileno())
    if events and valid_bytes and not lines[len(events) - 1].endswith(b"\n"):
        with path.open("ab") as handle:
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    return events


def restore_results(output: Path, cells: list[dict]) -> dict[str, dict]:
    events_path = output / "events.jsonl"
    events = load_events(events_path)
    results = {e["result"]["id"]: e["result"] for e in events if e.get("event") == "result"}
    for result in results.values():
        # Pre-transition append-only records intentionally remain unchanged on disk.
        result.setdefault("configuration_version", LEGACY_CONFIGURATION_VERSION)
        result.setdefault("max_tokens", 8192)
    starts = {e["cell"]["id"]: e for e in events if e.get("event") == "started"}
    for cell in cells:
        if cell["id"] in results or cell["id"] not in starts:
            continue
        started = starts[cell["id"]]
        pid = started.get("pid")
        if pid:
            try:
                command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
                if b"run_harness.py" in command and str(started["destination"]).encode() in command:
                    raise RuntimeError(f"prior episode process {pid} still runs; inspect it before resuming")
            except FileNotFoundError:
                pass
        result = read_result(cell, Path(started["destination"]), interrupted=True)
        append_event(events_path, {"event": "result", "result": result})
        results[cell["id"]] = result
    return results


def make_summary(cells: list[dict], results: dict, budget: dict, started_at: str, status: str, current=None) -> dict:
    def version_of(cell):
        row = results.get(cell["id"])
        return row.get("configuration_version", LEGACY_CONFIGURATION_VERSION) if row else CONFIGURATION_VERSION

    def counts(selected, version=None):
        rows = [results[c["id"]] for c in selected if c["id"] in results]
        if version is not None:
            rows = [row for row in rows if row.get("configuration_version", LEGACY_CONFIGURATION_VERSION) == version]
        outcomes = Counter(r["outcome"] for r in rows)
        valid_completed = outcomes["success"] + outcomes["failure"]
        mixed = len({row.get("configuration_version", LEGACY_CONFIGURATION_VERSION) for row in rows}) > 1
        return {"total": len(selected), "completed": len(rows), "valid_completed": valid_completed,
                "success": outcomes["success"], "failure": outcomes["failure"], "error": outcomes["error"],
                "interrupted": outcomes["interrupted"], "budget_stopped": outcomes["budget_stopped"], "notrun": len(selected) - len(rows),
                "success_rate_valid_completed": outcomes["success"] / valid_completed if valid_completed and not mixed else None,
                "mixed_configuration_versions": mixed}
    fresh = [r for r in results.values() if not r.get("imported_pilot")]
    elapsed = max(0.001, (datetime.now(timezone.utc) - datetime.fromisoformat(started_at)).total_seconds())
    summary = {"status": status, "updated_at_utc": now(), "started_at_utc": started_at, "counts": counts(cells),
               "coverage": counts([c for c in cells if c["seed"] == 0]),
               "per_suite": {suite: counts([c for c in cells if c["suite"] == suite]) for suite in SUITES},
               "budget": budget, "current_cell": current, "fresh_completed": len(fresh), "wall_elapsed_s": elapsed,
               "fresh_episodes_per_hour": len(fresh) * 3600 / elapsed,
               "pilot_reused": any(r.get("imported_pilot") for r in results.values()),
               "success_basis": "valid native environment terminated trace; not planner finish", "notrun_is_failure": False,
               "active_configuration_version": CONFIGURATION_VERSION,
               "conditional_output_upgrade": {**UPGRADE_RULE, "enabled": CONDITIONAL_UPGRADE_ENABLED,
                   "status": "triggered" if CONFIGURATION_VERSION == UPGRADED_CONFIGURATION_VERSION else "armed" if CONDITIONAL_UPGRADE_ENABLED else "not_configured"},
               "per_configuration": {version: {"max_tokens": VERSION_LIMITS[version],
                   "counts": counts([c for c in cells if version_of(c) == version], version),
                   "per_suite": {suite: counts([c for c in cells if c["suite"] == suite and version_of(c) == version], version) for suite in SUITES}}
                   for version in sorted({r.get("configuration_version", LEGACY_CONFIGURATION_VERSION) for r in results.values()} | {CONFIGURATION_VERSION})}}
    return summary


def migrate_output_limit(output: Path) -> dict:
    """Record the explicitly authorized8192->10000 change at a stopped boundary."""
    with (output / "runner.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old = json.loads((output / "config.json").read_text())
        if old["profile"]["max_tokens"] != 8192:
            raise ValueError("expected the original8192-token configuration")
        new = frozen_config(Path(old["budget_ledger"]), Path(old["pilot"]))
        if new["profile"] != {**old["profile"], "max_tokens": 10000}:
            raise ValueError("configuration transition must change only the output cap")
        results = restore_results(output, matrix())
        pending = [c for c in matrix() if c["id"] not in results]
        history = output / "configurations"
        history.mkdir(exist_ok=True)
        for version, value in ((LEGACY_CONFIGURATION_VERSION, old), (CONFIGURATION_VERSION, new)):
            path = history / f"{version}.json"
            with path.open("x") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        event = {"event": "configuration_changed", "from_version": LEGACY_CONFIGURATION_VERSION,
                 "to_version": CONFIGURATION_VERSION, "old_max_tokens": 8192, "new_max_tokens": 10000,
                 "old_config_sha256": digest(old), "new_config_sha256": digest(new), "at_utc": now(),
                 "previous_completed": len(results), "effective_first_cell": pending[0] if pending else None,
                 "budget_ledger": old["budget_ledger"], "cost_limit_usd": old["cost_limit_usd"]}
        atomic_json(output / "config.json", new)
        append_event(output / "events.jsonl", event)
        atomic_json(output / "configuration-history.json", {"versions": [LEGACY_CONFIGURATION_VERSION, CONFIGURATION_VERSION], "transition": event})
        return event


def _snapshot(path: Path, value: dict) -> None:
    if path.exists():
        if digest(json.loads(path.read_text())) != digest(value):
            raise ValueError("an immutable configuration snapshot already differs")
        return
    with path.open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _configuration_history(output: Path, event: dict, version: str | None = None) -> None:
    path = output / "configuration-history.json"
    history = json.loads(path.read_text()) if path.exists() else {"versions": []}
    if version and version not in history.setdefault("versions", []):
        history["versions"].append(version)
    history.setdefault("events", []).append(event)
    atomic_json(path, history)


def token_limit_trigger(result: dict) -> dict | None:
    """Accept only a failed10000-token episode's explicit SDK output-limit error."""
    if (result.get("configuration_version") != "v2-output-10000" or result.get("max_tokens") != 10000
            or result.get("outcome") not in ("failure", "error") or result.get("native_success") is True):
        return None
    path = Path(result["run_summary"])
    if not path.is_file():
        return None
    report = json.loads(path.read_text())
    maximum = report.get("max_tokens") or _flag(report.get("commands", {}).get("online_planner", []), "--max-tokens")
    error = report.get("planner_error") or report.get("error")
    if (str(maximum) != "10000" or not isinstance(error, str)
            or not re.search(r"\bModel token limit\s*\(\s*10000\s*\)\s+exceeded\b", error, re.IGNORECASE)):
        return None
    return {"cell": result["id"], "run_summary": str(path), "run_summary_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "planner_error": error, "from_max_tokens": 10000, "reason": "explicit_model_output_token_limit"}


def maybe_upgrade_output(output: Path, config: dict, results: dict) -> tuple[dict, dict | None]:
    """Run only at an episode boundary; one matching failure enables future32000."""
    if config.get("conditional_output_upgrade") != UPGRADE_RULE or config["profile"]["max_tokens"] != 10000:
        return config, None
    trigger = next((e for result in results.values() if (e := token_limit_trigger(result)) is not None), None)
    if trigger is None:
        return config, None
    pending = [c for c in matrix() if c["id"] not in results]
    if not pending:
        return config, None
    new = frozen_config(Path(config["budget_ledger"]), Path(config["pilot"]), max_tokens=32000, conditional_upgrade=True)
    if new["profile"] != {**config["profile"], "max_tokens": 32000}:
        raise ValueError("conditional upgrade may change only the output cap")
    history = output / "configurations"
    history.mkdir(exist_ok=True)
    _snapshot(history / "v3-output-32000.json", new)
    event = {"event": "conditional_output_upgrade_triggered", "from_version": "v2-output-10000",
             "to_version": UPGRADED_CONFIGURATION_VERSION, "old_max_tokens": 10000, "new_max_tokens": 32000,
             "at_utc": now(), "trigger": trigger, "previous_completed": len(results), "effective_first_cell": pending[0],
             "old_config_sha256": digest(config), "new_config_sha256": digest(new),
             "budget_ledger": config["budget_ledger"], "cost_limit_usd": config["cost_limit_usd"]}
    # Write the evidence before updating the active configuration. If execution
    # is interrupted here, the trigger remains available for inspection.
    atomic_json(output / "conditional-upgrade.json", {"status": "triggered", "rule": UPGRADE_RULE, "event": event})
    atomic_json(output / "config.json", new)
    append_event(output / "events.jsonl", event)
    _configuration_history(output, event, UPGRADED_CONFIGURATION_VERSION)
    return new, event


def arm_conditional_upgrade(output: Path) -> dict:
    """Explicitly add the user's conditional rule after the old runner stopped."""
    with (output / "runner.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old = json.loads((output / "config.json").read_text())
        if old["profile"]["max_tokens"] not in (10000, 32000):
            raise ValueError("conditional policy requires the current10000-token configuration")
        if old.get("conditional_output_upgrade") == UPGRADE_RULE:
            config, upgrade = maybe_upgrade_output(output, old, restore_results(output, matrix()))
            return {"already_armed": True, "active_configuration_version": config["configuration_version"], "upgrade_event": upgrade}
        if old["profile"]["max_tokens"] != 10000:
            raise ValueError("unconfigured32000 profile cannot be silently authorized")
        new = frozen_config(Path(old["budget_ledger"]), Path(old["pilot"]), max_tokens=10000, conditional_upgrade=True)
        if new["profile"] != old["profile"] or old["cost_limit_usd"] != "40":
            raise ValueError("arming the rule must preserve the current profile and budget")
        results = restore_results(output, matrix())
        pending = [c for c in matrix() if c["id"] not in results]
        history = output / "configurations"
        history.mkdir(exist_ok=True)
        _snapshot(history / "v2-output-10000-before-conditional-policy.json", old)
        _snapshot(history / "v2-output-10000-conditional-policy.json", new)
        event = {"event": "conditional_output_upgrade_armed", "at_utc": now(), "rule": UPGRADE_RULE,
                 "active_configuration_version": "v2-output-10000", "max_tokens": 10000,
                 "old_config_sha256": digest(old), "new_config_sha256": digest(new), "previous_completed": len(results),
                 "effective_first_cell": pending[0] if pending else None,
                 "budget_ledger": old["budget_ledger"], "cost_limit_usd": old["cost_limit_usd"]}
        atomic_json(output / "config.json", new)
        append_event(output / "events.jsonl", event)
        _configuration_history(output, event)
        atomic_json(output / "conditional-upgrade.json", {"status": "armed", "rule": UPGRADE_RULE, "event": event})
        config, upgrade = maybe_upgrade_output(output, new, results)
        return {"policy_event": event, "upgrade_event": upgrade, "active_configuration_version": config["configuration_version"]}


def run(args, config: dict) -> int:
    output = args.output_dir.resolve()
    config_hash = digest(config)
    if args.resume:
        stored = json.loads((output / "config.json").read_text())
        if digest(stored) != config_hash:
            raise ValueError("resume requires the exact frozen profile and source fingerprints")
    else:
        output.mkdir(parents=True, exist_ok=False)
        atomic_json(output / "config.json", config)
    activate_configuration(config)
    lock = (output / "runner.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError("another runner owns this output directory") from None
    cells = matrix()
    services = None
    active = None
    stop = False
    previous_handlers = {}
    started_at = now()
    previous_summary = output / "summary.json"
    if args.resume and previous_summary.is_file():
        started_at = json.loads(previous_summary.read_text()).get("started_at_utc", started_at)
    status = "running"
    results = {}
    try:
        def set_stop():
            nonlocal stop
            stop = True

        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda _sig, _frame: set_stop())

        results = restore_results(output, cells)
        if cells[0]["id"] not in results:
            pilot = validate_pilot(args.pilot.resolve())
            append_event(output / "events.jsonl", {"event": "result", "result": pilot})
            results[pilot["id"]] = pilot
        config, _ = maybe_upgrade_output(output, config, results)
        activate_configuration(config)
        budget = budget_snapshot(args.budget_ledger)
        atomic_json(output / "summary.json", make_summary(cells, results, budget, started_at, status))
        pending = [c for c in cells if c["id"] not in results]
        if pending and can_start(budget):
            sys.path.insert(0, str(ROOT / "scripts/harness"))
            from shared_model_services import SharedModelServices
            services = SharedModelServices(output / ("services-" + uuid4().hex[:10]))
            endpoints = services.start()
        else:
            endpoints = {}
        consecutive_errors = 0
        for cell in pending:
            budget = budget_snapshot(args.budget_ledger)
            if stop:
                status = "stopped_by_signal"
                break
            if not can_start(budget):
                status = "budget_stopped"
                break
            if shutil.disk_usage(output).free < 5 * 1024**3:
                status = "storage_blocked"
                break
            if services is None or not services.alive():
                status = "shared_service_failure"
                break
            destination = output / "episodes" / cell["id"].replace(":", "_")
            destination.parent.mkdir(exist_ok=True)
            if destination.exists():
                raise ValueError("unrecorded episode output exists; refusing a duplicate run")
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            environment.pop("LIBERO_SUFFIX", None)
            environment.pop("LIBERO_PERTURBATION", None)
            log = (output / (cell["id"].replace(":", "_") + ".driver.log")).open("wb")
            active = subprocess.Popen(episode_command(cell, destination, args.budget_ledger.resolve(), endpoints), cwd=ROOT, env=environment,
                                      stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            append_event(output / "events.jsonl", {"event": "started", "cell": cell, "destination": str(destination), "pid": active.pid, "at_utc": now(), "configuration_version": CONFIGURATION_VERSION, "max_tokens": PROFILE["max_tokens"]})
            interrupted_sent = False
            while active.poll() is None:
                budget = budget_snapshot(args.budget_ledger)
                atomic_json(output / "summary.json", make_summary(cells, results, budget, started_at, "running", cell))
                if stop and not interrupted_sent:
                    active.send_signal(signal.SIGINT)
                    interrupted_sent = True
                time.sleep(5)
            log.close()
            active = None
            result = read_result(cell, destination, interrupted=stop)
            append_event(output / "events.jsonl", {"event": "result", "result": result})
            results[cell["id"]] = result
            config, upgrade_event = maybe_upgrade_output(output, config, results)
            activate_configuration(config)
            budget = budget_snapshot(args.budget_ledger)
            atomic_json(output / "summary.json", make_summary(cells, results, budget, started_at, "running"))
            print(json.dumps({"cell": cell["id"], "outcome": result["outcome"], "completed": len(results), "accounted_upper_bound_usd": budget["accounted_upper_bound_usd"]}), flush=True)
            consecutive_errors = 0 if upgrade_event is not None else consecutive_errors + 1 if result["systemic_error"] else 0
            if result["budget_stopped"]:
                status = "budget_stopped"
                break
            if consecutive_errors >= 3:
                status = "stopped_on_repeated_infrastructure_errors"
                break
        else:
            status = "completed"
        return 0 if status in ("completed", "budget_stopped") else 1
    except BaseException:
        status = "blocked_exception"
        raise
    finally:
        # SIGINT asks the single-episode owner to close its own Env/Planner.
        # Do not start another episode or kill unrelated process groups.
        if active is not None and active.poll() is None:
            active.send_signal(signal.SIGINT)
            active.wait()
        if services is not None:
            services.close()
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        try:
            budget = budget_snapshot(args.budget_ledger)
            atomic_json(output / "summary.json", make_summary(cells, results, budget, started_at, status))
        finally:
            lock.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--budget-ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    config = config_for_resume(args.output_dir, args.budget_ledger, args.pilot) if args.resume and args.output_dir else frozen_config(args.budget_ledger, args.pilot)
    if not args.execute:
        print(json.dumps({"episodes": 2000, "coverage_first": 40, "pilot_reused": True, "new_episodes": 1999,
                          "profile": config["profile"], "config_sha256": digest(config), "budget_ledger": str(args.budget_ledger), "network_or_gpu_started": False}, indent=2))
        return 0
    if not args.output_dir or not os.environ.get("DEEPSEEK_API_KEY"):
        parser.error("execution requires --output-dir and environment-only DEEPSEEK_API_KEY")
    try:
        return run(args, config)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

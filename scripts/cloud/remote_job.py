#!/usr/bin/env python3
"""Linux/tmux job runner used over SSH by cloudctl; no third-party Python dependencies."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time


JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def root_path(value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute() or ".." in candidate.parts or candidate == Path("/"):
        raise ValueError("root must be an absolute project path, not / or a path containing ..")
    return candidate.resolve(strict=True)


def scoped_path(root: Path, value: str, *, allow_dot: bool = False) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or (value in {"", "."} and not allow_dot):
        raise ValueError("path must be a project-relative path without ..")
    resolved = (root / candidate).resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("path resolves outside the configured project root")
    return resolved


def job_path(root: Path, job_id: str) -> Path:
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("invalid job id: use up to 64 letters, digits, underscores or hyphens")
    candidate = root / ".cloud" / "jobs" / job_id
    if not candidate.resolve().is_relative_to(root):
        raise ValueError("job directory resolves outside project root")
    return candidate


def process_identity(pid: int) -> str | None:
    """Linux process start ticks protect stop/status against PID reuse."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return fields[19]  # starttime is /proc stat field 22; this list starts at field 3.
    except (OSError, IndexError):
        return None


def runner_alive(status: dict) -> bool:
    pid = status.get("runner_pid")
    identity = status.get("runner_start_ticks")
    return isinstance(pid, int) and identity is not None and process_identity(pid) == identity


def read_status(directory: Path) -> dict:
    status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
    if status["state"] == "running" and not runner_alive(status):
        # Reboots, SIGKILL, OOM, or tmux loss may leave an unfinished manifest.
        status = {**status, "state": "interrupted", "note": "runner is absent; inspect logs/checkpoints before restarting"}
    if status["state"] == "queued" and (directory / "stop.requested").exists():
        status = {**status, "state": "stop_requested", "note": "runner will cancel before executing the command"}
    return status


def start(root: Path, args: argparse.Namespace) -> dict:
    executable = shutil.which("tmux")
    if executable is None:
        raise ValueError("tmux is required on the server for detached jobs")
    argv = args.argv[1:] if args.argv and args.argv[0] == "--" else args.argv
    if not argv:
        raise ValueError("job command is empty")
    working_directory = scoped_path(root, args.cwd, allow_dot=True)
    if not working_directory.is_dir():
        raise ValueError("job cwd must be a directory")
    directory = job_path(root, args.id)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    spec = {"job_id": args.id, "argv": argv, "cwd": str(working_directory), "created_at": timestamp()}
    atomic_json(directory / "spec.json", spec)
    session = "ea-" + args.id
    status = {"job_id": args.id, "state": "queued", "tmux_session": session, "created_at": spec["created_at"]}
    atomic_json(directory / "status.json", status)
    wrapper = shlex.join([
        sys.executable, str(Path(__file__).resolve()), "--root", str(root), "_run", "--id", args.id,
    ])
    result = subprocess.run([executable, "new-session", "-d", "-s", session, wrapper], capture_output=True, text=True)
    if result.returncode:
        status.update(state="start_failed", error=result.stderr.strip(), exit_code=result.returncode)
        atomic_json(directory / "status.json", status)
        raise ValueError("tmux could not start job: " + result.stderr.strip())
    return read_status(directory)


def run_job(root: Path, job_id: str) -> int:
    directory = job_path(root, job_id)
    if (directory / "stop.requested").exists():
        atomic_json(directory / "status.json", {"job_id": job_id, "state": "stopped", "exit_code": 143, "finished_at": timestamp(), "note": "cancelled before command start"})
        return 143
    spec = json.loads((directory / "spec.json").read_text(encoding="utf-8"))
    cwd = Path(spec["cwd"]).resolve(strict=True)
    if not cwd.is_relative_to(root):
        raise ValueError("job cwd resolves outside project root")
    status = {
        "job_id": job_id, "state": "running", "started_at": timestamp(),
        "runner_pid": os.getpid(), "runner_start_ticks": process_identity(os.getpid()),
        "tmux_session": "ea-" + job_id,
    }
    process = None
    received_signal = None
    termination_deadline = None

    def signal_group(number: int) -> None:
        if process is not None:
            try:
                os.killpg(process.pid, number)
            except ProcessLookupError:
                pass

    def on_signal(number: int, _frame: object) -> None:
        nonlocal received_signal, termination_deadline
        received_signal = number
        termination_deadline = termination_deadline or time.monotonic() + 5.0
        signal_group(signal.SIGTERM)

    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, on_signal)
    # Publish the PID only after signal forwarding is ready.
    atomic_json(directory / "status.json", status)
    return_code = exit_code = 127
    try:
        with (directory / "console.log").open("ab", buffering=0) as log:
            if received_signal is not None or (directory / "stop.requested").exists():
                received_signal = received_signal or signal.SIGTERM
                return_code = exit_code = 143
            else:
                try:
                    process = subprocess.Popen(spec["argv"], cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                except OSError as exc:
                    log.write(("Cannot start command: " + str(exc) + "\n").encode())
                else:
                    status["child_pid"] = process.pid
                    atomic_json(directory / "status.json", status)
                    if received_signal is not None or (directory / "stop.requested").exists():
                        on_signal(received_signal or signal.SIGTERM, None)
                    while True:
                        try:
                            return_code = process.wait(timeout=0.1)
                            break
                        except subprocess.TimeoutExpired:
                            if termination_deadline is not None and time.monotonic() >= termination_deadline:
                                signal_group(signal.SIGKILL)
                    exit_code = return_code if return_code >= 0 else 128 - return_code
    finally:
        if process is not None:
            # Worker descendants can remain after the leader exits. Clean the known
            # process group on success, stop and exceptions; do not rely on poll().
            signal_group(signal.SIGTERM)
            deadline = termination_deadline or time.monotonic() + 5.0
            while process_group_alive(process.pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            if process_group_alive(process.pid):
                signal_group(signal.SIGKILL)
            if process.poll() is None:
                process.wait(timeout=5.0)
    if received_signal is not None:
        state = "stopped"
        exit_code = 128 + received_signal
    else:
        state = "succeeded" if exit_code == 0 else "failed"
    status.update(state=state, finished_at=timestamp(), exit_code=exit_code, child_return_code=return_code)
    atomic_json(directory / "status.json", status)
    return exit_code


def process_group_alive(pgid: int) -> bool:
    """Ignore zombies; a stopped leader may have surviving training workers."""
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if fields[0] != "Z" and int(fields[2]) == pgid:
                return True
        except (OSError, IndexError, ValueError):
            continue
    return False


def stop(directory: Path) -> dict:
    status = read_status(directory)
    if status["state"] not in {"queued", "stop_requested", "running"}:
        return {**status, "stop_requested": False}
    (directory / "stop.requested").touch(exist_ok=True)
    status = read_status(directory)
    if status["state"] in {"queued", "stop_requested"}:
        return {**status, "state": "stop_requested", "stop_requested": True}
    if status["state"] != "running":
        return {**status, "stop_requested": False}
    # The stored start ticks must still match before signalling the known runner.
    if not runner_alive(status):
        return {**status, "state": "interrupted", "stop_requested": False}
    os.kill(status["runner_pid"], signal.SIGTERM)
    return {**status, "stop_requested": True, "note": "TERM sent; poll status for the final exit code"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    commands = parser.add_subparsers(dest="operation", required=True)
    create = commands.add_parser("start")
    create.add_argument("--id", required=True)
    create.add_argument("--cwd", default=".")
    create.add_argument("argv", nargs=argparse.REMAINDER)
    for name in ("status", "stop", "_run"):
        sub = commands.add_parser(name)
        sub.add_argument("--id", required=True)
    logs = commands.add_parser("logs")
    logs.add_argument("--id", required=True)
    logs.add_argument("--lines", type=int, default=100)
    logs.add_argument("--follow", action="store_true")
    verify = commands.add_parser("verify-path")
    verify.add_argument("path")
    execute = commands.add_parser("exec")
    execute.add_argument("--cwd", default=".")
    execute.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        root = root_path(args.root)
        if args.operation == "verify-path":
            print(scoped_path(root, args.path))
            return 0
        if args.operation == "exec":
            argv = args.argv[1:] if args.argv and args.argv[0] == "--" else args.argv
            if not argv or not argv[0] or argv[0].startswith("-"):
                raise ValueError("command must begin with a program, not an option")
            return subprocess.call(argv, cwd=scoped_path(root, args.cwd, allow_dot=True))
        directory = job_path(root, args.id)
        if args.operation == "_run":
            return run_job(root, args.id)
        if args.operation == "start":
            result = start(root, args)
        elif args.operation == "status":
            result = read_status(directory)
        elif args.operation == "stop":
            result = stop(directory)
        else:
            if not 1 <= args.lines <= 10000:
                raise ValueError("lines must be between 1 and 10000")
            return subprocess.call(["tail", "-n", str(args.lines), *( ["-F"] if args.follow else []), str(directory / "console.log")])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        if args.operation == "_run":
            try:
                atomic_json(job_path(root, args.id) / "status.json", {"job_id": args.id, "state": "failed", "exit_code": 127, "finished_at": timestamp(), "error": str(exc)})
            except (OSError, ValueError, UnboundLocalError):
                pass
        print(f"Remote job error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

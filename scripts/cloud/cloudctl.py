#!/usr/bin/env python3
"""Preview SSH/rsync operations for a GPU server; --execute opts into network access.

Use an SSH host alias whose identity, port, user and verified host key are managed
outside the project by OpenSSH. No API, connector, or Python package is required.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import fnmatch
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "workspace" / "vla_baselines" / "cloud" / "config.example.json"
SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3"]
HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
EXCLUDES = (
    ".git/", ".agents/", ".codex/", ".ssh/", ".aws/", ".config/gcloud/", ".cloud/",
    ".env", ".env.*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "*credentials*", "*secrets*",
    "*.local.json", "__pycache__/", ".pytest_cache/", ".venv/", "venv/", ".venvs/", "node_modules/",
    "logs/", "log/", "runs/", "wandb/", "videos/", "recordings/", "artifacts/", "outputs/",
    "/workspace/vla_baselines/repos/", "/workspace/vla_baselines/cache/", "/workspace/vla_baselines/checkpoints/", "/workspace/vla_baselines/datasets/",
    "*.pt", "*.pth", "*.ckpt", "*.safetensors", "*.onnx", "*.bag", "*.db3", "*.mcap", "*.pcd", "*.ply", "*.npy", "*.npz", "*.parquet",
    "*.zip", "*.7z", "*.rar", "*.tar", "*.tar.gz", "*.tgz", "docs/对话*.md",
)


def clean_text(value: str) -> str:
    if not isinstance(value, str) or not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("configuration/path values must be nonempty strings without control characters")
    return value


def relative_path(value: str, *, allow_dot: bool = False) -> str:
    clean_text(value)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in value.split("/") or (str(path) == "." and not allow_dot):
        raise ValueError("path must be project-relative without ..")
    if any(char in value for char in "*?[]\\"):
        raise ValueError("use a literal path without glob patterns or backslashes")
    return str(path)


@dataclass(frozen=True)
class Config:
    ssh_host: str
    remote_root: str
    remote_python: str
    local_root: Path

    @classmethod
    def read(cls, path: Path, local_root: Path) -> "Config":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config must be a JSON object")
        unknown = set(data) - {"ssh_host", "remote_root", "remote_python"}
        if unknown:
            raise ValueError("unknown config keys: " + ", ".join(sorted(unknown)))
        host = clean_text(data["ssh_host"])
        if not HOST.fullmatch(host):
            raise ValueError("ssh_host must be a simple OpenSSH host alias, not a command, address or user@host")
        remote_root = clean_text(data["remote_root"])
        root_path = PurePosixPath(remote_root)
        if not root_path.is_absolute() or ".." in remote_root.split("/") or str(root_path) == "/":
            raise ValueError("remote_root must be an absolute project path without .., and cannot be /")
        interpreter = clean_text(data.get("remote_python", "python3"))
        if interpreter.startswith("-"):
            raise ValueError("remote_python cannot begin with -")
        resolved_local = local_root.expanduser().resolve(strict=True)
        if not resolved_local.is_dir():
            raise ValueError("local root must be a directory")
        return cls(host, str(root_path), interpreter, resolved_local)


def ssh_command(config: Config, argv: list[str]) -> list[str]:
    return ["ssh", *SSH_OPTIONS, config.ssh_host, shlex.join(argv)]


def worker_command(config: Config, argv: list[str]) -> list[str]:
    worker = str(PurePosixPath(config.remote_root) / "scripts" / "cloud" / "remote_job.py")
    return ssh_command(config, [config.remote_python, worker, "--root", config.remote_root, *argv])


def rsync_base() -> list[str]:
    return ["rsync", "-az", "--protect-args", "--safe-links", "--partial", "--itemize-changes", "-e", shlex.join(["ssh", *SSH_OPTIONS])]


def pull_destination(config: Config, relative: str) -> Path:
    base = config.local_root / "workspace" / "vla_baselines" / "artifacts" / "cloud" / config.ssh_host
    current = config.local_root
    for part in (base / relative).relative_to(config.local_root).parts:
        current /= part
        if current.is_symlink():
            raise ValueError("pull destination contains an existing symlink; choose a clean artifact path")
    return base


def command_argv(raw: list[str]) -> list[str]:
    argv = raw[1:] if raw and raw[0] == "--" else raw
    if not argv or not argv[0] or argv[0].startswith("-"):
        raise ValueError("command is empty or starts with an option; put a program after --")
    return argv


def build_commands(config: Config, args: argparse.Namespace) -> list[list[str]]:
    operation = args.operation
    if operation == "push":
        root = config.remote_root
        destination = config.ssh_host + ":" + root + "/"
        transfer = [*rsync_base(), *( [] if args.execute else ["--dry-run"]), *("--exclude=" + item for item in EXCLUDES), str(config.local_root) + "/", destination]
        # mkdir is also only a displayed plan until --execute is present.
        return [ssh_command(config, ["mkdir", "-p", root]), transfer]
    if operation == "pull":
        path = relative_path(args.path)
        credential_patterns = (".env*", ".ssh", ".aws", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "*credentials*", "*secrets*")
        if any(fnmatch.fnmatch(part.lower(), pattern) for part in PurePosixPath(path).parts for pattern in credential_patterns):
            raise ValueError("refusing a credential-like pull path")
        destination = pull_destination(config, path)
        # The server-side check rejects intermediate symlinks escaping the project.
        return [
            worker_command(config, ["verify-path", path]),
            ["mkdir", "-p", str(destination)],
            [*rsync_base(), "--relative", *( [] if args.execute else ["--dry-run"]), config.ssh_host + ":" + config.remote_root + "/./" + path, str(destination) + "/"],
        ]
    if operation == "exec":
        cwd = relative_path(args.cwd, allow_dot=True)
        argv = command_argv(args.argv)
        return [worker_command(config, ["exec", "--cwd", cwd, "--", *argv])]
    if operation == "doctor":
        return [ssh_command(config, [config.remote_python, str(PurePosixPath(config.remote_root) / "scripts/vla/doctor.py")])]
    if operation == "tunnel":
        for port in (args.local_port, args.remote_port):
            if not 1 <= port <= 65535:
                raise ValueError("ports must be between 1 and 65535")
        return [["ssh", *SSH_OPTIONS, "-o", "ExitOnForwardFailure=yes", "-N", "-L", f"127.0.0.1:{args.local_port}:127.0.0.1:{args.remote_port}", config.ssh_host]]
    if not JOB_ID.fullmatch(args.id):
        raise ValueError("invalid job id: use up to 64 letters, digits, underscores or hyphens")
    if operation == "job-start":
        cwd = relative_path(args.cwd, allow_dot=True)
        argv = command_argv(args.argv)
        job_args = ["start", "--id", args.id, "--cwd", cwd, "--", *argv]
    elif operation == "job-logs":
        if not 1 <= args.lines <= 10000:
            raise ValueError("lines must be between 1 and 10000")
        job_args = ["logs", "--id", args.id, "--lines", str(args.lines), *( ["--follow"] if args.follow else [])]
    else:
        job_args = [operation.removeprefix("job-"), "--id", args.id]
    return [worker_command(config, job_args)]


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--local-root", type=Path, default=ROOT)
    parser.add_argument("--execute", action="store_true", help="Perform the displayed network/remote operations; default only prints a plan")
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("push")
    pull = commands.add_parser("pull")
    pull.add_argument("path", help="One literal project-relative file or directory")
    execute = commands.add_parser("exec")
    execute.add_argument("--cwd", default=".")
    execute.add_argument("argv", nargs=argparse.REMAINDER)
    commands.add_parser("doctor")
    tunnel = commands.add_parser("tunnel")
    tunnel.add_argument("--local-port", type=int, required=True)
    tunnel.add_argument("--remote-port", type=int, required=True)
    create = commands.add_parser("job-start")
    create.add_argument("--id", required=True)
    create.add_argument("--cwd", default=".")
    create.add_argument("argv", nargs=argparse.REMAINDER)
    for operation in ("job-status", "job-stop"):
        sub = commands.add_parser(operation)
        sub.add_argument("--id", required=True)
    logs = commands.add_parser("job-logs")
    logs.add_argument("--id", required=True)
    logs.add_argument("--lines", type=int, default=100)
    logs.add_argument("--follow", action="store_true")
    return parser


def main() -> int:
    args = make_parser().parse_args()
    try:
        config = Config.read(args.config, args.local_root)
        commands = build_commands(config, args)
        print("# " + ("Execution requested." if args.execute else "Plan only: no network connection or remote/local artifact changes."), flush=True)
        for command in commands:
            print(shlex.join(command), flush=True)
        if not args.execute:
            return 0
        # Check every local tool before the first remote mutation (e.g. mkdir).
        for executable in dict.fromkeys(command[0] for command in commands):
            if shutil.which(executable) is None:
                raise ValueError(f"local executable is missing: {executable}")
        for command in commands:
            result = subprocess.run(command, check=False)
            if result.returncode:
                return result.returncode
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"Cloud operation error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

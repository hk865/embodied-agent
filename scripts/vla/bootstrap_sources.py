#!/usr/bin/env python3
"""Prepare pinned source trees without installing packages or downloading weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace" / "vla_baselines"


def validate_source(source: dict) -> tuple[str, str]:
    url, commit = source["url"], source["commit"]
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        raise ValueError("Sources must use an HTTPS github.com URL")
    slug = parsed.path.removesuffix(".git").strip("/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", slug):
        raise ValueError(f"Invalid source repository: {slug}")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"Source must have a full pinned commit: {slug}")
    return slug, commit


def run_git(args: list[str], cwd: Path) -> str:
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(
        ["git", "-c", "http.lowSpeedLimit=1024", "-c", "http.lowSpeedTime=30", *args],
        cwd=cwd, env=env, capture_output=True, text=True, check=True, timeout=120,
    )
    return result.stdout.strip()


def fetch_archive(source: dict, target: Path, stage: Path) -> str:
    slug, commit = validate_source(source)
    archive = stage / "source.tar.gz"
    request = Request(f"https://codeload.github.com/{slug}/tar.gz/{commit}",
                      headers={"User-Agent": "embodied-agent-source-preparation"})
    digest = hashlib.sha256()
    size = 0
    with urlopen(request, timeout=30) as response, archive.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 256 * 1024 * 1024:
                raise ValueError("Source archive exceeds the 256 MiB preparation limit")
            digest.update(chunk)
            output.write(chunk)
    extracted = stage / "extracted"
    extracted.mkdir()
    with tarfile.open(archive) as bundle:
        bundle.extractall(extracted, filter="data")
    directories = list(extracted.iterdir())
    if len(directories) != 1 or not directories[0].is_dir():
        raise ValueError("Unexpected archive structure")
    target.parent.mkdir(parents=True, exist_ok=True)
    directories[0].rename(target)
    return digest.hexdigest()


def check_git_submodules(target: Path) -> None:
    status = run_git(["submodule", "status", "--recursive"], target)
    if any(line.startswith(("-", "+", "U")) for line in status.splitlines()):
        raise ValueError(f"Git submodules are missing or differ from the pinned tree: {target}")


def prepare(name: str, source: dict, repos: Path, method: str) -> dict:
    _, commit = validate_source(source)
    target = repos / name
    receipt_path = target / ".source-receipt.json"
    if target.exists():
        if receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text())
            if receipt.get("url") == source["url"] and receipt.get("commit") == commit:
                if receipt.get("method") == "archive":
                    keys = ("path", "url", "commit")
                    expected = [{key: item[key] for key in keys}
                                for item in source.get("archive_submodules", [])]
                    observed = [{key: item.get(key) for key in keys}
                                for item in receipt.get("submodules", [])]
                    if observed != expected:
                        raise ValueError(f"Archive submodule receipt differs from the lock: {target}")
                else:
                    if run_git(["rev-parse", "HEAD"], target) != commit:
                        raise ValueError(f"Git HEAD differs from the receipt: {target}")
                    if run_git(["status", "--porcelain", "--untracked-files=no"], target):
                        raise ValueError(f"Git source has tracked local changes: {target}")
                    check_git_submodules(target)
                print(f"{name}: already prepared; source files have not been integrity-audited")
                return receipt
        if method == "git" and (target / ".git").is_dir():
            head = run_git(["rev-parse", "HEAD"], target)
            if head == commit and not run_git(["status", "--porcelain"], target):
                check_git_submodules(target)
                return {"url": source["url"], "commit": commit, "method": "git", "status": "existing_clean"}
        raise ValueError(f"Refusing to replace an existing or mismatched source tree: {target}")

    repos.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=repos) as temporary:
        stage = Path(temporary)
        checkout = stage / "checkout"
        receipt = {"url": source["url"], "commit": commit, "method": method}
        if method == "git":
            checkout.mkdir()
            run_git(["init", "--quiet"], checkout)
            run_git(["remote", "add", "origin", source["url"]], checkout)
            run_git(["fetch", "--depth", "1", "origin", commit], checkout)
            run_git(["checkout", "--quiet", "--detach", "FETCH_HEAD"], checkout)
            if run_git(["rev-parse", "HEAD"], checkout) != commit:
                raise ValueError(f"Commit verification failed for {name}")
            run_git(["submodule", "update", "--init", "--recursive", "--depth", "1"], checkout)
        else:
            receipt["archive_sha256"] = fetch_archive(source, checkout, stage)
            receipt["submodules"] = []
            for index, submodule in enumerate(source.get("archive_submodules", [])):
                relative = Path(submodule["path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Invalid archive submodule path")
                subtarget = checkout / relative
                if subtarget.exists():
                    subtarget.rmdir()  # Only the empty placeholder in our new snapshot.
                substage = stage / f"submodule-{index}"
                substage.mkdir()
                checksum = fetch_archive(submodule, subtarget, substage)
                receipt["submodules"].append(dict(submodule, archive_sha256=checksum))
        receipt["status"] = "source_prepared_only"
        (checkout / ".source-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        checkout.rename(target)
    print(f"{name}: prepared {commit}")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=WORKSPACE / "sources.lock.json")
    parser.add_argument("--workspace", type=Path, default=WORKSPACE)
    parser.add_argument("--only", nargs="+", help="Repository names from the lock")
    parser.add_argument("--method", choices=("git", "archive"), default="git")
    parser.add_argument("--execute", action="store_true", help="Download source code; default only prints the plan")
    args = parser.parse_args()
    lock = json.loads(args.lock.read_text())
    repositories = lock["repositories"]
    selected = args.only or list(repositories)
    try:
        for name in selected:
            if not re.fullmatch(r"[\w-]+", name) or name not in repositories:
                raise ValueError(f"Unknown repository name: {name}")
            validate_source(repositories[name])
        if not args.execute:
            for name in selected:
                print(f"{name}: {repositories[name]['commit']} -> {args.workspace / 'repos' / name} ({args.method})")
            print("Plan only. Use --execute to prepare sources. Dependencies and weights are separate.")
            return 0
        if args.method == "git" and not shutil.which("git"):
            raise ValueError("git is unavailable; use --method archive")
        output = args.workspace / "artifacts" / "sources.receipts.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        receipts = json.loads(output.read_text()) if output.is_file() else {}
        for name in selected:
            receipts[name] = prepare(name, repositories[name], args.workspace / "repos", args.method)
            output.write_text(json.dumps(receipts, indent=2) + "\n")
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f"Preparation incomplete: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

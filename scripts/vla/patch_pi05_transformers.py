#!/usr/bin/env python3
"""Apply openpi's required Transformers replacement to the isolated server only."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
import sysconfig


ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace" / "vla_baselines"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    expected = WORKSPACE / ".venvs" / "pi05-server"
    if Path(sys.prefix).resolve() != expected.resolve():
        parser.error("Run this using the isolated .venvs/pi05-server/bin/python")
    if importlib.metadata.version("transformers") != "4.53.2":
        parser.error("The pinned openpi replacements require Transformers 4.53.2")
    source = WORKSPACE / "repos" / "openpi" / "src" / "openpi" / "models_pytorch" / "transformers_replace"
    destination = Path(sysconfig.get_path("purelib")) / "transformers"
    expected_files = {
        "models/gemma/configuration_gemma.py", "models/gemma/modeling_gemma.py",
        "models/paligemma/modeling_paligemma.py", "models/siglip/modeling_siglip.py", "models/siglip/check.py",
    }
    observed_files = {str(path.relative_to(source)) for path in source.rglob("*.py")}
    if not source.is_dir() or observed_files != expected_files:
        parser.error("The pinned source must contain exactly the five official replacement files")
    records = []
    for path in sorted(source.rglob("*.py")):
        relative = path.relative_to(source)
        target = destination / relative
        original = digest(target) if target.exists() else None
        target.parent.mkdir(parents=True, exist_ok=True)
        # Replace the file inode as well: do not mutate a linked package cache.
        staged = target.with_suffix(".pi05-new")
        shutil.copyfile(path, staged)
        staged.replace(target)
        if digest(target) != digest(path):
            raise RuntimeError(f"Patch hash mismatch: {relative}")
        records.append({"path": str(relative), "original_sha256": original, "patched_sha256": digest(target)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"status": "patched", "environment": sys.prefix, "files": records}, indent=2) + "\n")
    print(f"Applied and verified {len(records)} official replacement files")


if __name__ == "__main__":
    main()

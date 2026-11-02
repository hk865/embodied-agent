#!/usr/bin/env python3
"""Validate the embodied-agent paper library without network access."""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
PAPERS_CSV = ROOT / "data" / "papers.csv"
REQUIRED_COLUMNS = {
    "paper_id",
    "title",
    "year",
    "track",
    "topic",
    "priority",
    "baseline_role",
    "benchmarks",
    "paper_url",
    "evidence",
    "read_status",
}
VALID_PRIORITIES = {"P0", "P1", "P2"}
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
VLA_RUNTIME_ROOTS = tuple(
    ROOT / "workspace" / "vla_baselines" / name
    for name in ("repos", "cache", "checkpoints", "datasets", "artifacts", "logs", "videos", ".venvs")
)


def validate_csv() -> tuple[list[str], int]:
    errors: list[str] = []
    with PAPERS_CSV.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_COLUMNS - columns)
        if missing_columns:
            errors.append(f"papers.csv 缺少字段: {', '.join(missing_columns)}")
        rows = list(reader)

    ids = [row.get("paper_id", "").strip() for row in rows]
    duplicates = sorted(key for key, count in Counter(ids).items() if key and count > 1)
    if duplicates:
        errors.append(f"papers.csv 存在重复 paper_id: {', '.join(duplicates)}")

    for line_number, row in enumerate(rows, start=2):
        for column in REQUIRED_COLUMNS:
            if not row.get(column, "").strip():
                errors.append(f"papers.csv:{line_number} 缺少 {column}")

        paper_id = row.get("paper_id", "")
        if not re.fullmatch(r"\d{4}\.\d{5}", paper_id):
            errors.append(f"papers.csv:{line_number} paper_id 格式错误: {paper_id}")

        year = row.get("year", "")
        if not year.isdigit() or not 1900 <= int(year) <= 2100:
            errors.append(f"papers.csv:{line_number} year 格式错误: {year}")

        priority = row.get("priority", "")
        if priority not in VALID_PRIORITIES:
            errors.append(f"papers.csv:{line_number} priority 非法: {priority}")

        paper_url = row.get("paper_url", "")
        if not paper_url.startswith(("https://", "http://")):
            errors.append(f"papers.csv:{line_number} paper_url 非 HTTP(S): {paper_url}")

        local_note = row.get("local_note", "").strip()
        if local_note.startswith("docs/") and not (ROOT / local_note).is_file():
            errors.append(f"papers.csv:{line_number} 本地卡片不存在: {local_note}")

    return errors, len(rows)


def validate_markdown_links() -> tuple[list[str], int]:
    errors: list[str] = []
    checked = 0
    for markdown_file in sorted(ROOT.rglob("*.md")):
        if any(markdown_file.is_relative_to(directory) for directory in VLA_RUNTIME_ROOTS):
            continue
        text = markdown_file.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>")
            if raw_target.startswith("<") and raw_target.endswith(">"):
                continue
            if re.match(r"^/?[A-Za-z]:/", target):
                continue
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue

            target = unquote(target.split("#", 1)[0])
            if not target:
                continue

            checked += 1
            local_path = (markdown_file.parent / target).resolve()
            if not local_path.exists():
                relative_source = markdown_file.relative_to(ROOT)
                errors.append(f"{relative_source}: 站内链接不存在 -> {raw_target}")

    return errors, checked


def main() -> int:
    csv_errors, paper_count = validate_csv()
    link_errors, link_count = validate_markdown_links()
    errors = csv_errors + link_errors

    print(f"论文条目: {paper_count}")
    print(f"已检查站内链接: {link_count}")
    if errors:
        print(f"发现 {len(errors)} 个问题:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("论文库检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

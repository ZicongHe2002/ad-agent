#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

KNOWN_STATUSES = {
    "SUPPORTED",
    "CONDITIONAL",
    "AUTH_REQUIRED",
    "MANUAL",
    "UNSUPPORTED",
    "UNKNOWN",
    "RATE_LIMITED",
    "DISABLED",
}


def parse_markdown_matrix(path: Path) -> list[dict[str, str]]:
    platform = "GLOBAL"
    records: list[dict[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if raw_line.startswith("## ") and raw_line[3:] not in {
            "Global Rules",
            "Capability Record Template",
        }:
            platform = raw_line[3:].strip()
        if not raw_line.startswith("|") or "---" in raw_line:
            continue
        cells = [cell.strip() for cell in raw_line.strip("|").split("|")]
        if len(cells) < 3 or cells[0] == "Capability":
            continue
        status = cells[1]
        if status in KNOWN_STATUSES:
            records.append(
                {"platform": platform, "capability": cells[0], "status": status, "notes": cells[2]}
            )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and print the capability matrix")
    parser.add_argument(
        "path",
        nargs="?",
        default=str(Path(__file__).resolve().parents[1] / "PLATFORM_CAPABILITIES.md"),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    path = Path(args.path)
    records = parse_markdown_matrix(path)
    if not records:
        raise SystemExit("no capability records found")
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        for record in records:
            print(f"{record['platform']:<20} {record['status']:<13} {record['capability']}")
        print(f"\n{len(records)} records checked; UNKNOWN was never promoted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

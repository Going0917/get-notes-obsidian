#!/usr/bin/env python3
"""
Remove visible Get IDs from Obsidian filenames while keeping frontmatter IDs.

Example:
  2026-07-10_get-1915206677704115056_电商直购链路与直播加粉业务讨论会.md
  -> 2026-07-10_电商直购链路与直播加粉业务讨论会.md
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
from datetime import datetime
from pathlib import Path


DEFAULT_ROOT = Path(
    "/Users/gogolin/Library/Mobile Documents/iCloud~md~obsidian/"
    "Documents/Going Knowledge/Get笔记沉淀"
)


def clean_name(name: str) -> str:
    cleaned = re.sub(r"_get-\d+_", "_", name)
    cleaned = re.sub(r"_get-\d+(?=\.md$)", "", cleaned)
    cleaned = re.sub(r"__+", "_", cleaned)
    return cleaned


def unique_path(path: Path, reserved: set[Path] | None = None) -> Path:
    reserved = reserved or set()
    if not path.exists() and path not in reserved:
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists() and candidate not in reserved:
            return candidate
    raise RuntimeError(f"Unable to find free path for {path}")


def planned_renames(root: Path) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    reserved: set[Path] = set()
    for path in sorted(root.rglob("*.md")):
        cleaned = clean_name(path.name)
        if cleaned == path.name:
            continue
        target = unique_path(path.with_name(cleaned), reserved)
        reserved.add(target)
        actions.append({
            "source": path.relative_to(root).as_posix(),
            "target": target.relative_to(root).as_posix(),
            "old_stem": path.stem,
            "new_stem": target.stem,
        })
    return actions


def update_sync_log(root: Path, actions: list[dict[str, str]], apply: bool) -> bool:
    log_path = root / "00-同步日志.md"
    if not log_path.exists():
        return False
    content = log_path.read_text(encoding="utf-8")
    updated = content
    for action in actions:
        updated = updated.replace(f"[[{action['old_stem']}\\|", f"[[{action['new_stem']}\\|")
        updated = updated.replace(f"[[{action['old_stem']}|", f"[[{action['new_stem']}|")
    if updated != content and apply:
        log_path.write_text(updated, encoding="utf-8")
    return updated != content


def write_report(actions: list[dict[str, str]], report_dir: Path, log_changed: bool) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "visible_id_renames.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["source", "target", "old_stem", "new_stem"])
        writer.writeheader()
        writer.writerows(actions)

    lines = [
        "# Visible Get ID Cleanup",
        "",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"Renames: {len(actions)}",
        f"Sync log links changed: {'yes' if log_changed else 'no'}",
        "",
    ]
    for action in actions:
        lines.append(f"- `{action['source']}` -> `{action['target']}`")
    (report_dir / "visible_id_cleanup.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_renames(root: Path, actions: list[dict[str, str]]) -> None:
    for action in actions:
        source = root / action["source"]
        target = root / action["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = args.report_dir or (Path(__file__).parent.parent / "cleanup_reports" / f"visible-id-{stamp}")
    actions = planned_renames(args.root)
    log_changed = update_sync_log(args.root, actions, args.apply)
    if args.apply:
        apply_renames(args.root, actions)
    write_report(actions, report_dir, log_changed)

    print(("APPLIED" if args.apply else "DRY RUN") + f": {len(actions)} renames")
    print(f"Sync log links changed: {'yes' if log_changed else 'no'}")
    print(f"Report: {report_dir}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
One-off cleanup for the Get notes Obsidian sink.

The script is intentionally conservative:
- never deletes note files
- moves duplicate files outside the sync root
- writes a CSV + Markdown report for every planned/applied move
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_ROOT = Path(
    "/Users/gogolin/Library/Mobile Documents/iCloud~md~obsidian/"
    "Documents/Going Knowledge/Get笔记沉淀"
)
DEFAULT_KNOWLEDGE_ROOT = DEFAULT_ROOT.parent
LEGACY_TOPS = {"AI与技术", "生活", "自我成长", "财富与投资"}

WORK_MEETING = ["会议", "沟通", "讨论会", "分享会", "客户沟通", "汇报"]
WORK_PROJECT = ["答辩", "OKR", "年度规划", "项目复盘", "复盘", "季度"]
WORK_GENERAL = [
    "工作", "职场", "业务", "运营", "电商", "视频号", "投放", "广告",
    "商家", "直播", "品牌", "私域", "腾讯", "合作", "客户", "618",
    "Q3", "Q4", "增长", "营销", "商务", "团队",
]
TRAVEL_REGIONS = {
    "05_旅行/日本": ["日本", "京都", "大阪", "奈良", "东京", "关西"],
    "05_旅行/东南亚": ["泰国", "曼谷", "清迈", "巴厘岛", "新加坡", "马来西亚", "越南", "柬埔寨"],
    "05_旅行/国内": ["国内旅行", "上海", "北京", "深圳", "广州", "香港", "成都", "西安"],
}
TOPIC_RULES = [
    ("03_财商投资", ["财富", "投资", "理财", "FIRE", "复利", "财商", "资产", "股东信", "巴菲特", "被动收入"]),
    ("01_AI与科技", ["AI", "人工智能", "大模型", "LLM", "Claude", "GPT", "Kimi", "技术", "工程", "编程", "提示词", "Obsidian"]),
    ("04_自我成长", ["成长", "女性", "认知", "表达", "效率", "习惯", "人际", "心理", "英语", "学习", "思维"]),
    ("06_生活/运动健康", ["跑步", "马拉松", "健身", "训练", "装备", "运动", "健康", "睡眠", "激素", "皮质醇"]),
    ("06_生活/消费选品", ["选品", "好物", "选购", "音箱", "消费"]),
]


@dataclass
class NoteFile:
    path: Path
    rel: str
    fm: dict[str, str]
    title: str

    @property
    def note_id(self) -> str | None:
        note_id = self.fm.get("id", "").strip()
        return note_id or None

    @property
    def top(self) -> str:
        return self.rel.split("/", 1)[0]

    @property
    def date(self) -> str:
        date = self.fm.get("date", "").strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", date):
            return date[:10]
        match = re.search(r"(20\d{2}-\d{2}-\d{2})", self.path.name)
        return match.group(1) if match else "unknown"

    @property
    def raw_get_id(self) -> str:
        note_id = self.note_id or ""
        return note_id[4:] if note_id.startswith("get-") else note_id


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:100]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def extract_title(text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    if not match:
        return fallback
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    title = re.sub(r"^《(.+)》—\s*读书笔记$", r"\1", title)
    title = re.sub(r"^语音备忘｜\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}.*$", "语音备忘", title)
    return title or fallback


def load_notes(root: Path) -> list[NoteFile]:
    notes: list[NoteFile] = []
    for path in sorted(root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        notes.append(NoteFile(path, rel, parse_frontmatter(text), extract_title(text, path.stem)))
    return notes


def score_keep(note: NoteFile) -> int:
    score = 0
    if re.match(r"^0[0-8]_", note.top):
        score += 100
    if note.top in LEGACY_TOPS:
        score -= 80
    if note.note_id and f"get-{note.raw_get_id}" in note.path.name:
        score += 70
    if note.fm.get("type") == "voice" and note.top == "07_语音日记":
        score += 80
    if note.top == "02_职场工作":
        score += 25
    if "/会议记录/" in note.rel or "/项目复盘/" in note.rel:
        score += 15
    if "_语音备忘_" in note.path.name:
        score -= 5
    return score


def sanitize(text: str, max_len: int = 54) -> str:
    text = re.sub(r'[/\\:*?"<>|]', "", text)
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] or "未命名"


def target_dir(note: NoteFile) -> str:
    note_type = note.fm.get("type", "")
    search = f"{note.title} {note.path.stem} {note.fm.get('tags', '')}"

    if note_type == "voice":
        month = note.date[:7] if note.date != "unknown" else "unknown"
        return f"07_语音日记/{month}"

    if note_type == "book":
        return "08_读书笔记"

    if any(word in search for word in WORK_GENERAL):
        if any(word in search for word in WORK_MEETING):
            return "02_职场工作/会议记录"
        if any(word in search for word in WORK_PROJECT):
            return "02_职场工作/项目复盘"
        return "02_职场工作"

    for directory, keywords in TRAVEL_REGIONS.items():
        if any(word in search for word in keywords):
            return directory

    for directory, keywords in TOPIC_RULES:
        if any(word in search for word in keywords):
            return directory

    if note.top == "AI与技术":
        return "01_AI与科技"
    if note.top == "自我成长":
        return "04_自我成长"
    if note.top == "财富与投资":
        return "03_财商投资"
    return "06_生活"


def target_filename(note: NoteFile) -> str:
    if not note.note_id:
        return note.path.name
    if note.fm.get("type") == "voice":
        return f"{note.date}_语音备忘.md"
    return f"{note.date}_{sanitize(note.title)}.md"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to find free path for {path}")


def make_plan(root: Path, archive_root: Path) -> list[dict[str, str]]:
    notes = load_notes(root)
    by_id: defaultdict[str, list[NoteFile]] = defaultdict(list)
    by_rel = {note.rel: note for note in notes}
    for note in notes:
        if note.note_id:
            by_id[note.note_id].append(note)

    actions: list[dict[str, str]] = []
    keep_rels: set[str] = set()

    for note_id, group in by_id.items():
        if len(group) == 1:
            keep_rels.add(group[0].rel)
            continue
        keep = max(group, key=score_keep)
        keep_rels.add(keep.rel)
        for note in group:
            if note.rel == keep.rel:
                continue
            actions.append({
                "action": "archive_duplicate",
                "id": note_id,
                "source": note.rel,
                "target": (archive_root / "duplicates" / note.rel).as_posix(),
                "keep": keep.rel,
                "reason": "same frontmatter id",
            })

    for rel in sorted(keep_rels):
        note = by_rel[rel]
        if note.top not in LEGACY_TOPS:
            continue
        destination = root / target_dir(note) / target_filename(note)
        if destination == note.path:
            continue
        actions.append({
            "action": "move_legacy_unique",
            "id": note.note_id or "",
            "source": note.rel,
            "target": destination.relative_to(root).as_posix(),
            "keep": "",
            "reason": "legacy top-level category",
        })

    return actions


def write_reports(actions: list[dict[str, str]], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "cleanup_actions.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["action", "id", "source", "target", "keep", "reason", "applied_target"])
        writer.writeheader()
        for action in actions:
            writer.writerow(action)

    counts: defaultdict[str, int] = defaultdict(int)
    for action in actions:
        counts[action["action"]] += 1
    md_lines = [
        "# Get Notes Cleanup Report",
        "",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Summary",
        "",
    ]
    for action, count in sorted(counts.items()):
        md_lines.append(f"- {action}: {count}")
    md_lines += ["", "## Files", ""]
    for action in actions:
        md_lines.append(
            f"- `{action['action']}` `{action['source']}` -> `{action['target']}`"
            + (f" (keep `{action['keep']}`)" if action["keep"] else "")
        )
    (report_dir / "cleanup_report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")


def apply_actions(root: Path, actions: list[dict[str, str]]) -> None:
    for action in actions:
        source = root / action["source"]
        if action["action"] == "archive_duplicate":
            target = Path(action["target"])
        else:
            target = root / action["target"]
        if not source.exists():
            action["applied_target"] = "missing-source"
            continue
        target = unique_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        action["applied_target"] = target.as_posix()

    # Remove empty legacy directories after moves. This never removes files.
    for directory in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not directory.is_dir():
            continue
        try:
            directory.rmdir()
        except OSError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--archive-root", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_root = args.archive_root or (DEFAULT_KNOWLEDGE_ROOT / f"_Get笔记重复归档_{stamp}")
    report_dir = args.report_dir or (Path(__file__).parent.parent / "cleanup_reports" / stamp)

    actions = make_plan(args.root, archive_root)
    if args.apply:
        apply_actions(args.root, actions)
    write_reports(actions, report_dir)

    counts: defaultdict[str, int] = defaultdict(int)
    for action in actions:
        counts[action["action"]] += 1
    mode = "APPLIED" if args.apply else "DRY RUN"
    print(f"{mode}: {len(actions)} planned actions")
    for action, count in sorted(counts.items()):
        print(f"  {action}: {count}")
    print(f"Report: {report_dir}")
    print(f"Archive root: {archive_root}")


if __name__ == "__main__":
    main()

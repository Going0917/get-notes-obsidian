#!/usr/bin/env python3
"""
Reorganize the current Get notes Obsidian sink to the 2026-07-11 taxonomy.

This is a conservative move-only script:
- no note contents are rewritten
- frontmatter IDs are preserved
- destination collisions get _2, _3 suffixes
- a CSV/Markdown report is written for every planned/applied move
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


DEFAULT_ROOT = Path(
    "/Users/gogolin/Library/Mobile Documents/iCloud~md~obsidian/"
    "Documents/Going Knowledge/Get笔记沉淀"
)

DOC_NAMES = {"00-同步工具维护日志.md", "00-同步规范.md", "00-同步日志.md"}


@dataclass
class Note:
    path: Path
    root: Path
    fm: dict[str, str]
    title: str
    text: str

    @property
    def rel(self) -> str:
        return self.path.relative_to(self.root).as_posix()

    @property
    def top(self) -> str:
        return self.rel.split("/", 1)[0]

    @property
    def type(self) -> str:
        return self.fm.get("type", "")

    @property
    def source_url(self) -> str:
        return self.fm.get("url") or self.fm.get("source_url") or ""

    @property
    def date(self) -> str:
        date = self.fm.get("date", "")
        if re.match(r"^20\d{2}-\d{2}-\d{2}", date):
            return date[:10]
        match = re.search(r"(20\d{2}-\d{2}-\d{2})", self.path.name)
        return match.group(1) if match else "unknown"

    @property
    def search(self) -> str:
        return f"{self.title} {self.path.name} {self.fm.get('tags', '')}"


def parse_frontmatter(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    if not text.startswith("---"):
        return data
    for line in text.splitlines()[1:120]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return re.sub(r"\s+", " ", line[2:].strip())
    return fallback


def load_notes(root: Path) -> list[Note]:
    notes: list[Note] = []
    for path in sorted(root.rglob("*.md")):
        if path.parent == root and path.name in DOC_NAMES:
            continue
        text = path.read_text(encoding="utf-8")
        notes.append(Note(path, root, parse_frontmatter(text), extract_title(text, path.stem), text))
    return notes


def contains(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def sanitize(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[/\\:*?"<>|]', "", name)
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len] or "未命名"


def voice_recording_datetime(note: Note) -> tuple[str, str]:
    match = re.search(r"语音备忘｜(20\d{2}-\d{2}-\d{2})\s+(\d{2}):(\d{2})", note.title)
    if match:
        rec_date = match.group(1)
        hour = int(match.group(2))
        minute = match.group(3)
        diary = datetime.strptime(rec_date, "%Y-%m-%d")
        if hour < 6:
            diary -= timedelta(days=1)
        return diary.strftime("%Y-%m-%d"), f"{hour:02d}{minute}"
    match = re.match(r"(20\d{2}-\d{2}-\d{2})(?:_(\d{4,6}))?", note.path.name)
    if match:
        time_part = (match.group(2) or "0000")[:4]
        return match.group(1), time_part
    return note.date, "0000"


def target_filename(note: Note) -> str:
    if note.type == "voice":
        diary_date, hhmm = voice_recording_datetime(note)
        return f"{diary_date}_{hhmm}_语音日记.md"
    title = sanitize(note.title)
    if note.date == "unknown" and title.startswith("unknown_"):
        return f"{title}.md"
    return f"{note.date}_{title}.md"


def classify_english(note: Note) -> str | None:
    if note.type == "english-learning" or contains(note.search, ["英语", "哑巴英语", "元宝App"]):
        if contains(note.search, ["场景", "咖啡馆", "餐厅", "机场", "酒店", "问路", "交通"]):
            return "09_英语学习/口语场景"
        return "09_英语学习/学习计划"
    return None


def classify_finance(note: Note) -> str | None:
    if contains(note.search, ["财富", "投资", "理财", "FIRE", "复利", "纳瓦尔", "资产配置", "凯利", "股东信", "巴菲特", "被动收入"]):
        return "03_财商投资"
    return None


def classify_growth(note: Note) -> str | None:
    if contains(note.search, ["表达", "影响力", "说教", "沟通困境", "人际关系"]):
        return "04_自我成长/04_关系与沟通"
    if contains(note.search, ["焦虑", "情绪", "心理", "不抱怨", "虚无主义", "创伤", "空心人", "对抗焦虑"]):
        return "04_自我成长/02_心理与情绪"
    if contains(note.search, ["职场妈妈", "职业倦怠", "职场困境", "初入职场", "职场人", "工作伦理", "职业心态"]):
        return "04_自我成长/03_职业心态与成长"
    if contains(note.search, ["成长", "时间管理", "奥德赛", "自我探索", "人生", "钱理群", "女性", "认知"]):
        return "04_自我成长/01_认知与表达"
    return None


def classify_life(note: Note) -> str | None:
    if contains(note.search, ["睡眠", "激素", "皮质醇", "过度训练", "跳箱", "镁离子", "健身", "训练恢复"]):
        return "06_生活/运动健康"
    if contains(note.search, ["极简", "蛋糕", "生活转型"]):
        return "06_生活"
    return None


BRAND_RULES = [
    ("华大营养", ["华大", "华大营养"]),
    ("诺特兰德", ["诺特兰德", "林诺德"]),
    ("星盟", ["星盟"]),
    ("万益蓝", ["万益蓝", "万叶兰"]),
    ("养元健", ["养元健", "养能健"]),
    ("多燕瘦", ["多燕瘦"]),
    ("Swisse", ["Swisse", "Swiss"]),
    ("谷雨", ["谷雨"]),
]


def classify_work(note: Note) -> str | None:
    text = note.search
    for brand, keywords in BRAND_RULES:
        if contains(text, keywords):
            return f"02_职场工作/01_客户沟通复盘/{brand}"

    if contains(text, ["P12", "P13", "晋升", "答辩"]):
        return "02_职场工作/03_内部汇报与项目复盘/晋升答辩"
    if contains(text, ["OKR", "规划", "季度", "年度"]):
        return "02_职场工作/03_内部汇报与项目复盘/OKR与业务规划"
    if contains(text, ["内部", "分享", "汇报", "高潜", "创享会"]):
        return "02_职场工作/03_内部汇报与项目复盘/内部分享"
    if contains(text, ["Codex", "AI工具", "AI赋能", "商销AI", "素材标签", "AI落地", "AI应用"]):
        return "02_职场工作/04_AI工具与业务提效"
    if contains(text, ["私域", "公私域"]):
        return "02_职场工作/02_业务主题研究/私域与公私域联动"
    if contains(text, ["视频号", "小店", "直播", "闭环", "电商直购"]):
        return "02_职场工作/02_业务主题研究/视频号小店与直播电商"
    if contains(text, ["投放", "广告", "RTA", "智投", "预算", "链路"]):
        return "02_职场工作/02_业务主题研究/投放与广告策略"
    if contains(text, ["内容力", "商品力", "开品", "选品", "功效标签", "经营力"]):
        return "02_职场工作/02_业务主题研究/内容力与商品力"
    if contains(text, ["大健康", "营养", "保健品", "膳食", "益生菌"]):
        return "02_职场工作/02_业务主题研究/大健康与营养品类"
    if note.top == "02_职场工作":
        return "02_职场工作/99_待归类"
    return None


def target_dir(note: Note) -> str:
    if note.type == "voice":
        diary_date, _ = voice_recording_datetime(note)
        return f"07_语音日记/{diary_date[:7]}"

    for classifier in (classify_english, classify_finance):
        result = classifier(note)
        if result:
            return result

    # Work is prioritized for current work notes and obvious business/customer material.
    work_result = classify_work(note)
    if work_result and (note.top == "02_职场工作" or contains(note.search, ["客户", "业务", "电商", "广告", "投放", "腾讯", "商销", "视频号", "保健品", "营养", "开品"])):
        # External self-growth podcasts currently misplaced in 02 should leave work first.
        if note.source_url and "xiaoyuzhoufm.com" in note.source_url and classify_growth(note):
            return classify_growth(note) or work_result
        return work_result

    for classifier in (classify_growth, classify_life):
        result = classifier(note)
        if result:
            return result

    if work_result:
        return work_result

    return note.path.parent.relative_to(note.root).as_posix()


def unique_path(path: Path, reserved: set[Path]) -> Path:
    if not path.exists() and path not in reserved:
        return path
    stem = path.stem
    suffix = path.suffix
    for i in range(2, 1000):
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists() and candidate not in reserved:
            return candidate
    raise RuntimeError(f"Unable to find free path for {path}")


def plan_actions(root: Path) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    reserved: set[Path] = set()
    for note in load_notes(root):
        destination = root / target_dir(note) / target_filename(note)
        if destination == note.path:
            reserved.add(destination)
            continue
        destination = unique_path(destination, reserved)
        reserved.add(destination)
        actions.append({
            "source": note.rel,
            "target": destination.relative_to(root).as_posix(),
            "type": note.type,
            "title": note.title,
        })
    return actions


def write_report(actions: list[dict[str, str]], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    with (report_dir / "reorganize_actions.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["source", "target", "type", "title"])
        writer.writeheader()
        writer.writerows(actions)

    lines = [
        "# Get Notes Reorganize Report",
        "",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"Moves: {len(actions)}",
        "",
    ]
    for action in actions:
        lines.append(f"- `{action['source']}` -> `{action['target']}`")
    (report_dir / "reorganize_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_actions(root: Path, actions: list[dict[str, str]]) -> None:
    for action in actions:
        source = root / action["source"]
        target = root / action["target"]
        if not source.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))

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
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = args.report_dir or (Path(__file__).parent.parent / "cleanup_reports" / f"reorganize-{stamp}")
    actions = plan_actions(args.root)
    if args.apply:
        apply_actions(args.root, actions)
    write_report(actions, report_dir)

    print(("APPLIED" if args.apply else "DRY RUN") + f": {len(actions)} moves")
    print(f"Report: {report_dir}")


if __name__ == "__main__":
    main()

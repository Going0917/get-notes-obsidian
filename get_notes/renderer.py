"""
renderer.py — 输出 Obsidian Markdown

根据笔记内容（tags + 标题关键词）路由到对应主题目录，生成 Markdown 文件并写入 Obsidian Vault。

目录结构（按主题，不按来源）：
    {vault}/01_AI与科技/{date}_{标题}.md
    {vault}/02_职场工作/01_客户沟通复盘/{客户}/{date}_{标题}.md
    {vault}/02_职场工作/02_业务主题研究/{主题}/{date}_{标题}.md
    {vault}/02_职场工作/03_内部汇报与项目复盘/{主题}/{date}_{标题}.md
    {vault}/02_职场工作/04_AI工具与业务提效/{date}_{标题}.md
    {vault}/02_职场工作/99_待归类/{date}_{标题}.md
    {vault}/03_财商投资/{date}_{标题}.md
    {vault}/04_自我成长/{主题}/{date}_{标题}.md
    {vault}/05_旅行/{地区}/{date}_{标题}.md
    {vault}/06_生活/{主题}/{date}_{标题}.md
    {vault}/07_语音日记/YYYY-MM/{diary_date}_{HHMM}_语音日记.md
    {vault}/08_读书笔记/{date}_{标题}.md
    {vault}/09_英语学习/{主题}/{date}_{标题}.md
"""
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from .config import config
from .parser import (
    ParsedNote,
    NOTE_TYPE_PODCAST, NOTE_TYPE_VOICE,
    NOTE_TYPE_ARTICLE, NOTE_TYPE_BOOK, NOTE_TYPE_WORK,
)

# 旅行地区关键词路由（字典驱动，新增国家/地区只需在此添加一行，无需修改路由逻辑）
_TRAVEL_REGIONS = {
    "05_旅行/日本":  ["日本", "京都", "大阪", "奈良", "东京", "关西", "日本旅游"],
    "05_旅行/东南亚": ["泰国", "曼谷", "清迈", "巴厘岛", "新加坡", "马来西亚", "越南"],
    "05_旅行/国内":  ["国内旅行", "上海", "北京", "深圳", "广州", "香港", "成都", "西安", "国内旅游"],
    # 后续扩展示例（取消注释即可启用）：
    # "05_旅行/欧洲":   ["巴黎", "伦敦", "罗马", "阿姆斯特丹", "柏林", "西班牙", "意大利"],
    # "05_旅行/美洲":   ["纽约", "洛杉矶", "旧金山", "加拿大", "墨西哥"],
}

_WORK_BRAND_RULES = [
    ("华大营养", ["华大", "华大营养"]),
    ("诺特兰德", ["诺特兰德", "林诺德"]),
    ("星盟", ["星盟"]),
    ("万益蓝", ["万益蓝", "万叶兰"]),
    ("养元健", ["养元健", "养能健"]),
    ("多燕瘦", ["多燕瘦"]),
    ("Swisse", ["Swisse", "Swiss"]),
    ("谷雨", ["谷雨"]),
]

_WORK_TOPIC_RULES = [
    ("02_业务主题研究/视频号小店与直播电商", ["视频号", "直播", "小店", "618", "电商", "GMV", "货架"]),
    ("02_业务主题研究/投放与广告策略", ["广告", "投放", "智投", "预算", "ROI", "消耗", "转化"]),
    ("02_业务主题研究/私域与公私域联动", ["私域", "公私域", "企微", "社群", "营销云"]),
    ("02_业务主题研究/内容力与商品力", ["内容力", "商品力", "素材", "达人", "种草", "短视频"]),
    ("02_业务主题研究/大健康与营养品类", ["大健康", "营养", "保健品", "膳食", "益生菌"]),
    ("03_内部汇报与项目复盘/晋升答辩", ["晋升", "答辩"]),
    ("03_内部汇报与项目复盘/OKR与业务规划", ["OKR", "okr", "年度规划", "季度规划", "Q3", "Q4", "行业规划"]),
    ("03_内部汇报与项目复盘/内部分享", ["汇报", "分享", "训练营", "团队", "内部"]),
    ("04_AI工具与业务提效", ["AI", "人工智能", "智能体", "Agent", "工具", "提效", "自动化"]),
]

# 主题关键词路由规则（按优先级顺序检查，第一个匹配的生效）
# 注意：旅行路由已移至 _TRAVEL_REGIONS 字典，由 _get_topic_path() 优先处理
_FINANCE_KEYWORDS = ["财富", "投资", "理财", "FIRE", "纳瓦尔", "复利", "财商", "资产配置", "股东信", "巴菲特", "被动收入", "凯利"]
_AI_KEYWORDS = [
    "AI", "人工智能", "大模型", "LLM", "Claude", "GPT", "Kimi",
    "Codex", "Agent", "飞书CLI", "技术", "工程", "编程", "提示词",
    "Obsidian知识管理",
]
_ENGLISH_KEYWORDS = ["英语", "哑巴英语", "元宝App"]
_WORK_KEYWORDS = ["客户", "业务", "电商", "广告", "投放", "腾讯", "商销", "视频号", "保健品", "营养", "开品", "会议", "复盘"]

_GROWTH_RULES = [
    ("04_自我成长/04_关系与沟通", ["表达", "影响力", "说教", "沟通困境", "人际关系"]),
    ("04_自我成长/02_心理与情绪", ["焦虑", "情绪", "心理", "不抱怨", "虚无主义", "创伤", "空心人", "对抗焦虑"]),
    ("04_自我成长/03_职业心态与成长", ["职场妈妈", "职业倦怠", "职场困境", "初入职场", "职场人", "工作伦理", "职业心态"]),
    ("04_自我成长/01_认知与表达", ["成长", "时间管理", "奥德赛", "自我探索", "人生", "钱理群", "女性", "认知", "超级个体"]),
]

_LIFE_RULES = [
    ("06_生活/运动健康", ["睡眠", "激素", "皮质醇", "过度训练", "跳箱", "镁离子", "健身", "训练恢复"]),
    ("06_生活/消费选品", ["选品", "好物", "选购", "音箱", "消费"]),
    ("06_生活", ["极简", "生活转型", "蛋糕"]),
]


def _voice_diary_date(note: "ParsedNote") -> str:
    """
    返回语音日记的"日记日期"。

    凌晨 00:00–05:59 录制的内容，通常是前一天的日记，归入前一天。
    例：2026-06-02 02:28 录制 → 日记日期 2026-06-01
    """
    from datetime import timedelta
    try:
        ts = note.created_at.replace("Z", "+00:00").replace(" ", "T")
        dt = datetime.fromisoformat(ts)
        if dt.hour < 6:
            dt -= timedelta(days=1)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return note.created_date


def _short_date(date_str: str) -> str:
    """Convert YYYY-MM-DD to YY.MM.DD for reader-friendly filenames."""
    match = re.match(r"^20(\d{2})-(\d{2})-(\d{2})", date_str or "")
    if not match:
        return date_str or "unknown"
    return f"{match.group(1)}.{match.group(2)}.{match.group(3)}"


def _search_text(note: "ParsedNote") -> str:
    # 路由只使用标题、标签和来源，避免正文里的泛关键词造成跨主题误判。
    return " ".join([
        " ".join(note.tags),
        note.title or "",
        note.source_name or "",
        note.source_url or "",
    ])


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _is_external_podcast(note: "ParsedNote") -> bool:
    return note.note_type == NOTE_TYPE_PODCAST and "xiaoyuzhoufm.com" in (note.source_url or "")


def _is_external_platform_article(note: "ParsedNote") -> bool:
    source_url = note.source_url or ""
    return note.note_type == NOTE_TYPE_ARTICLE and any(
        domain in source_url for domain in ("xhslink.com", "xiaohongshu.com", "xhs.cn")
    )


def _get_work_path(note: "ParsedNote", search_text: str) -> str:
    brand_search_text = " ".join([search_text, note.summary or "", note.body_text or ""])
    for brand, keywords in _WORK_BRAND_RULES:
        if _contains_any(brand_search_text, keywords):
            return f"02_职场工作/01_客户沟通复盘/{brand}"

    for suffix, keywords in _WORK_TOPIC_RULES:
        if _contains_any(search_text, keywords):
            return f"02_职场工作/{suffix}"

    return "02_职场工作/99_待归类"


def _get_rule_path(search_text: str, rules: list[tuple[str, list[str]]]) -> Optional[str]:
    for path, keywords in rules:
        if _contains_any(search_text, keywords):
            return path
    return None


def _get_topic_path(note: "ParsedNote") -> str:
    """
    根据笔记的 tags 和标题关键词，返回主题目录路径（相对于 vault 根目录）。

    优先级顺序：
    1. voice 类型 → "07_语音日记/YYYY-MM"（按月分组）
    2. work 类型  → 按客户/业务主题/内部复盘分流
    3. book 类型  → 直接返回 "08_读书笔记"
    4. 旅行关键词 → 遍历 _TRAVEL_REGIONS 字典（新增国家只改配置，不改此函数）
    5. 主题关键词 → 英语/财商/成长/生活/AI
    6. 无匹配    → 兜底返回 "06_生活"
    """
    if note.note_type == NOTE_TYPE_VOICE:
        month = _voice_diary_date(note)[:7]  # 凌晨录音归前一天的月份
        return f"07_语音日记/{month}"

    search_text = _search_text(note)

    if note.note_type == NOTE_TYPE_WORK:
        return _get_work_path(note, search_text)

    if note.note_type == NOTE_TYPE_BOOK:
        return "08_读书笔记"

    # 旅行路由（字典驱动，可扩展）
    for travel_dir, keywords in _TRAVEL_REGIONS.items():
        if _contains_any(search_text, keywords):
            return travel_dir

    if note.note_type == "english-learning" or _contains_any(search_text, _ENGLISH_KEYWORDS):
        if _contains_any(search_text, ["场景", "咖啡馆", "餐厅", "机场", "酒店", "问路", "交通"]):
            return "09_英语学习/口语场景"
        return "09_英语学习/学习计划"

    if _contains_any(search_text, _FINANCE_KEYWORDS):
        return "03_财商投资"

    # 外部平台内容不按“职场工作”归档，除非已经被解析为 work。
    if (
        not _is_external_podcast(note)
        and not _is_external_platform_article(note)
        and _contains_any(search_text, _WORK_KEYWORDS)
    ):
        return _get_work_path(note, search_text)

    growth_path = _get_rule_path(search_text, _GROWTH_RULES)
    if growth_path:
        return growth_path

    life_path = _get_rule_path(search_text, _LIFE_RULES)
    if life_path:
        return life_path

    ai_search_text = search_text
    if _is_external_platform_article(note):
        ai_search_text = " ".join([note.title or "", note.source_name or ""])
    if _contains_any(ai_search_text, _AI_KEYWORDS):
        return "01_AI与科技"

    return "06_生活"  # 兜底


class ObsidianRenderer:
    def __init__(self, vault_path: Path = None):
        self.vault = vault_path or config.obsidian_vault
        self._id_index = None
        self._duplicate_ids = {}

    # ────────────────────────────────────────────────
    # 公开接口
    # ────────────────────────────────────────────────

    def get_output_path(self, note: ParsedNote) -> Path:
        """计算目标文件路径（不创建文件）"""
        topic_path = _get_topic_path(note)   # 如 "AI与技术" 或 "旅行/日本"
        filename   = self._make_filename(note)
        return self.vault / topic_path / filename

    def render(self, note: ParsedNote) -> str:
        """根据笔记类型生成 Markdown 字符串"""
        template_map = {
            NOTE_TYPE_PODCAST: self._render_podcast,
            NOTE_TYPE_VOICE:   self._render_voice,
            NOTE_TYPE_ARTICLE: self._render_article,
            NOTE_TYPE_BOOK:    self._render_book,
            NOTE_TYPE_WORK:    self._render_work,
        }
        renderer_fn = template_map.get(note.note_type, self._render_unknown)
        return renderer_fn(note)

    def existing_note_count(self) -> int:
        """返回 vault 中已索引的 Get 笔记 ID 数量。"""
        self._ensure_id_index()
        return len(self._id_index)

    def duplicate_id_count(self) -> int:
        """返回 vault 中重复出现的 Get 笔记 ID 数量。"""
        self._ensure_id_index()
        return len(self._duplicate_ids)

    def write(self, note: ParsedNote, dry_run: bool = False) -> tuple[Path, bool, str]:
        """
        渲染并写入文件。

        参数：
            dry_run: True 时只打印路径，不实际写入

        返回：
            (目标文件路径, 是否新写入, 原因)
        """
        existing_path = self.find_existing_path(note)
        if existing_path:
            return existing_path, False, "existing-id"

        output_path = self.get_output_path(note)

        if dry_run:
            print(f"  [dry-run] → {output_path}")
            return output_path, True, "dry-run"

        # 目录不存在则创建
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # ID 去重已经在 find_existing_path() 完成；这里仅处理不同笔记撞名。
        output_path = _unique_path(output_path)

        content = self.render(note)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        self._remember_written_note(note, output_path)
        return output_path, True, "written"

    def find_existing_path(self, note: ParsedNote) -> Optional[Path]:
        """按 frontmatter 中的 Get 笔记 ID 在整个 vault 内查找已存在文件。"""
        self._ensure_id_index()
        return self._id_index.get(_frontmatter_id(note))

    def _ensure_id_index(self):
        """构建 id -> path 索引，避免目录/文件名规则变化后重复写入。"""
        if self._id_index is not None:
            return

        self._id_index = {}
        duplicates = {}
        if not self.vault.exists():
            self._duplicate_ids = duplicates
            return

        for path in sorted(self.vault.rglob("*.md")):
            note_id = _extract_frontmatter_id(path)
            if not note_id:
                continue
            if note_id in self._id_index:
                duplicates.setdefault(note_id, [self._id_index[note_id]]).append(path)
                continue
            self._id_index[note_id] = path

        self._duplicate_ids = duplicates

    def _remember_written_note(self, note: ParsedNote, path: Path):
        """写入新文件后更新内存索引，防止同一轮重复处理。"""
        self._ensure_id_index()
        self._id_index[_frontmatter_id(note)] = path

    # ────────────────────────────────────────────────
    # 模板渲染
    # ────────────────────────────────────────────────

    def _render_podcast(self, note: ParsedNote) -> str:
        synced_at = _now_iso()
        source_line = ""
        if note.source_url:
            source_line = f"[{note.source_name or note.source_url}]({note.source_url})"
        else:
            source_line = note.source_name or "未知来源"

        duration = f"｜时长：{note.duration_display}" if note.duration_display else ""
        date_str = note.created_date

        tags_yaml = _yaml_list(["podcast"] + note.tags)

        lines = [
            "---",
            f"id: get-{note.id}",
            "type: podcast",
            f'source: "{_escape_yaml(note.source_name or "")}"',
            f'episode: "{_escape_yaml(note.title)}"',
            f"url: {note.source_url or ''}",
            f"date: {date_str}",
            f"tags: {tags_yaml}",
            f"synced_at: {synced_at}",
            "---",
            "",
            f"# {note.title}",
            "",
            f"> 来源：{source_line}{duration}｜{date_str}",
            "",
            "---",
        ]

        # 收集本文档的 section，用于生成目录
        sections = []
        if note.summary:
            sections.append(("📝 AI 总结", "📝-ai-总结"))
        if note.chapters:
            sections.append(("🏷 重点章节", "🏷-重点章节"))
        if note.quotes:
            sections.append(("💬 金句摘录", "💬-金句摘录"))
        if note.body_text:
            sections.append(("📄 AI 笔记", "📄-ai-笔记"))
        if note.transcript:
            sections.append(("📃 原文转写", "📃-原文转写"))

        lines += _toc(sections)

        if note.summary:
            lines += ["", "## 📝 AI 总结", "", note.summary, ""]

        if note.chapters:
            lines += ["", "## 🏷 重点章节", ""]
            for ch in note.chapters:
                header = f"### {ch.timestamp} — {ch.title}" if ch.timestamp else f"### {ch.title}"
                lines.append(header)
                if ch.content:
                    lines += [ch.content, ""]

        if note.quotes:
            lines += ["", "## 💬 金句摘录", ""]
            for q in note.quotes:
                lines += [_quote_line(q), ""]

        # body_text（AI 结构化笔记）和 transcript（原文转写）各自独立输出，互不覆盖
        if note.body_text:
            lines += ["", "## 📄 AI 笔记", "", note.body_text, ""]

        if note.transcript:
            lines += ["", "## 📃 原文转写", "", note.transcript, ""]

        return "\n".join(lines)

    def _render_voice(self, note: ParsedNote) -> str:
        synced_at = _now_iso()
        date_str = note.created_date
        time_display = note.created_at[11:16] if len(note.created_at) >= 16 else ""
        duration = f"｜时长：{note.duration_display}" if note.duration_display else ""
        tags_yaml = _yaml_list(["voice-memo"] + note.tags)

        lines = [
            "---",
            f"id: get-{note.id}",
            "type: voice",
            f"date: {date_str}",
            f"duration: {note.duration_display or '未知'}",
            f"tags: {tags_yaml}",
            f"synced_at: {synced_at}",
            "---",
            "",
            f"# 语音备忘｜{date_str} {time_display}{duration}",
            "",
            "---",
        ]

        # 语音日记只保留整理后的笔记内容；不输出原始录音转写、摘要或摘录。
        note_content = note.body_text or note.summary
        if note_content:
            lines += ["", "## 📝 笔记内容", "", note_content, ""]

        return "\n".join(lines)

    def _render_article(self, note: ParsedNote) -> str:
        synced_at = _now_iso()
        date_str = note.created_date
        tags_yaml = _yaml_list(["article"] + note.tags)

        source_line = ""
        if note.source_url:
            source_line = f"[{note.source_name or note.source_url}]({note.source_url})"
        else:
            source_line = note.source_name or ""

        lines = [
            "---",
            f"id: get-{note.id}",
            "type: article",
            f"source_url: {note.source_url or ''}",
            f'source_name: "{_escape_yaml(note.source_name or "")}"',
            f"date: {date_str}",
            f"tags: {tags_yaml}",
            f"synced_at: {synced_at}",
            "---",
            "",
            f"# {note.title}",
            "",
        ]

        if source_line:
            lines += [f"> 来源：{source_line}｜{date_str}", ""]

        lines.append("---")

        sections = []
        if note.summary:
            sections.append(("📝 我的笔记 / AI 总结", "📝-我的笔记--ai-总结"))
        if note.quotes:
            sections.append(("💬 划线金句", "💬-划线金句"))
        if note.body_text:
            sections.append(("📄 AI 笔记", "📄-ai-笔记"))
        if note.transcript:
            sections.append(("📃 链接原文", "📃-链接原文"))

        lines += _toc(sections)

        if note.summary:
            lines += ["", "## 📝 我的笔记 / AI 总结", "", note.summary, ""]

        if note.quotes:
            lines += ["", "## 💬 划线金句", ""]
            for q in note.quotes:
                lines += [_quote_line(q), ""]

        if note.body_text:
            lines += ["", "## 📄 AI 笔记", "", note.body_text, ""]

        if note.transcript:
            lines += ["", "## 📃 链接原文", "", note.transcript, ""]

        return "\n".join(lines)

    def _render_book(self, note: ParsedNote) -> str:
        synced_at = _now_iso()
        date_str = note.created_date
        tags_yaml = _yaml_list(["book", "reading"] + note.tags)

        lines = [
            "---",
            f"id: get-{note.id}",
            "type: book",
            f'book_title: "{_escape_yaml(note.source_name or note.title)}"',
            f"date: {date_str}",
            f"tags: {tags_yaml}",
            f"synced_at: {synced_at}",
            "---",
            "",
            f"# 《{note.source_name or note.title}》— 读书笔记",
            "",
            "---",
        ]

        sections = []
        if note.summary:
            sections.append(("💡 核心洞察", "💡-核心洞察"))
        if note.quotes:
            sections.append(("💬 书摘", "💬-书摘"))
        if note.body_text:
            sections.append(("📄 完整笔记", "📄-完整笔记"))

        lines += _toc(sections)

        if note.summary:
            lines += ["", "## 💡 核心洞察", "", note.summary, ""]

        if note.quotes:
            lines += ["", "## 💬 书摘", ""]
            for q in note.quotes:
                lines += [_quote_line(q), ""]

        if note.body_text:
            lines += ["", "## 📄 完整笔记", "", note.body_text, ""]

        return "\n".join(lines)

    def _render_work(self, note: ParsedNote) -> str:
        synced_at = _now_iso()
        date_str = note.created_date
        tags_yaml = _yaml_list(["工作笔记"] + note.tags)

        source_line = ""
        if note.source_url:
            source_line = f"[{note.source_name or note.source_url}]({note.source_url})"
        elif note.source_name:
            source_line = note.source_name

        lines = [
            "---",
            f"id: get-{note.id}",
            "type: work",
            f"source_url: {note.source_url or ''}",
            f'source_name: "{_escape_yaml(note.source_name or "")}"',
            f"date: {date_str}",
            f"tags: {tags_yaml}",
            f"synced_at: {synced_at}",
            "---",
            "",
            f"# {note.title}",
            "",
        ]

        if source_line:
            lines += [f"> 来源：{source_line}｜{date_str}", ""]

        lines.append("---")

        sections = []
        if note.summary:
            sections.append(("📝 核心要点", "📝-核心要点"))
        if note.quotes:
            sections.append(("💬 关键摘录", "💬-关键摘录"))
        if note.body_text:
            sections.append(("📄 完整内容", "📄-完整内容"))
        if note.transcript:
            sections.append(("🎙 原文转写", "🎙-原文转写"))

        lines += _toc(sections)

        if note.summary:
            lines += ["", "## 📝 核心要点", "", note.summary, ""]

        if note.quotes:
            lines += ["", "## 💬 关键摘录", ""]
            for q in note.quotes:
                lines += [_quote_line(q), ""]

        if note.body_text:
            lines += ["", "## 📄 完整内容", "", note.body_text, ""]

        # 工作笔记需要保留会议原文，便于回看真实对话细节。
        if note.transcript:
            lines += ["", "## 🎙 原文转写", "", note.transcript, ""]

        return "\n".join(lines)

    def _render_unknown(self, note: ParsedNote) -> str:
        synced_at = _now_iso()
        date_str = note.created_date
        tags_yaml = _yaml_list(note.tags)

        lines = [
            "---",
            f"id: get-{note.id}",
            "type: unknown",
            f"date: {date_str}",
            f"tags: {tags_yaml}",
            f"synced_at: {synced_at}",
            "---",
            "",
            f"# {note.title}",
            "",
        ]

        sections = []
        if note.summary:
            sections.append(("📝 摘要", "📝-摘要"))
        if note.body_text:
            sections.append(("📄 内容", "📄-内容"))
        if note.transcript:
            sections.append(("🎙 转写", "🎙-转写"))

        lines += _toc(sections)

        if note.summary:
            lines += ["## 📝 摘要", "", note.summary, ""]
        if note.body_text:
            lines += ["## 📄 内容", "", note.body_text, ""]
        if note.transcript:
            lines += ["## 🎙 转写", "", note.transcript, ""]

        return "\n".join(lines)

    # ────────────────────────────────────────────────
    # 文件名生成
    # ────────────────────────────────────────────────

    def _make_filename(self, note: ParsedNote) -> str:
        """
        生成安全的文件名（不含非法字符，长度合理）

        格式：
        - 播客/文章/读书/工作：{YY.MM.DD}_{标题}.md
        - 语音备忘：{YY.MM.DD}_{HHMM}_语音日记.md（凌晨录音归前一天）

        Get 笔记 ID 只保存在 frontmatter 中，用于机器去重，不暴露在文件名里。
        """
        date = _short_date(note.created_date)  # 26.03.15

        if note.note_type == NOTE_TYPE_VOICE:
            return f"{_short_date(_voice_diary_date(note))}_{note.created_time_str[:4]}_语音日记.md"

        parts = [date]  # 日期前缀便于排序；ID 留在 frontmatter 中做全局去重
        if note.title:
            title_clean = _sanitize(note.title, max_len=40)
            if title_clean:
                parts.append(title_clean)

        return "_".join(p for p in parts if p) + ".md"


# ────────────────────────────────────────────────────────
# 工具函数
# ────────────────────────────────────────────────────────

def _toc(sections: list) -> list:
    """
    生成 Markdown 目录超链接块。
    仅当 sections 数量 >= 2 时才生成，否则返回空列表。

    参数：
        sections: [(显示文字, anchor), ...]
        anchor 使用 Obsidian 兼容的小写+连字符格式

    示例输出：
        **目录：** [📝 AI 总结](#-ai-总结) · [📄 原文内容](#-原文内容)
    """
    if len(sections) < 2:
        return []
    links = " · ".join(f"[{label}](#{anchor})" for label, anchor in sections)
    return ["", f"**目录：** {links}", ""]


def _sanitize(text: str, max_len: int = 50) -> str:
    """去除文件名中的非法字符，截断长度"""
    if not text:
        return ""
    # 去除 macOS/Linux 文件名非法字符
    text = re.sub(r'[/\\:*?"<>|]', "", text)
    # 去除控制字符
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    # 压缩多余空白
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _unique_path(path: Path) -> Path:
    """Return a non-existing sibling path by appending _2, _3 ... when needed."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for i in range(2, 1000):
        candidate = path.parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"无法为文件生成唯一名称：{path}")


def _frontmatter_id(note: ParsedNote) -> str:
    """返回当前同步器写入 frontmatter 时使用的稳定 ID。"""
    raw_id = str(note.id or "").strip()
    return raw_id if raw_id.startswith("get-") else f"get-{raw_id}"


def _extract_frontmatter_id(path: Path) -> Optional[str]:
    """从 Markdown frontmatter 中提取 id 字段。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            first = f.readline().strip()
            if first != "---":
                return None
            for _ in range(80):
                line = f.readline()
                if not line:
                    return None
                stripped = line.strip()
                if stripped == "---":
                    return None
                if stripped.startswith("id:"):
                    return stripped.split(":", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def _escape_yaml(text: str) -> str:
    """转义 YAML frontmatter 中的双引号"""
    return text.replace('"', '\\"')


def _yaml_list(tags: list) -> str:
    """生成 YAML 列表字符串，去重"""
    seen = set()
    unique = []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    if not unique:
        return "[]"
    return "[" + ", ".join(unique) + "]"


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 字符串"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _quote_line(text: str) -> str:
    """生成 Markdown 引用格式的金句行（兼容 Python 3.9）"""
    return "> \u201c" + text + "\u201d"

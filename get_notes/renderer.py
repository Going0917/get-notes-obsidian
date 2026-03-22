"""
renderer.py — 输出 Obsidian Markdown

根据笔记类型选择对应模板，生成 Markdown 文件并写入 Obsidian Vault。

目录结构（按内容主题域组织，而非来源媒介）：
    {vault}/播客笔记/{主题子目录}/{date}_{标题}.md
        主题子目录：AI与科技 / 自我成长 / 财商投资 / 其他播客
        注：AI 主题的文章也会路由到此处，与播客内容合并
    {vault}/工作笔记/{date}_{标题}.md
    {vault}/旅行/{国家或地区}/{date}_{标题}.md
    {vault}/生活决策/{子目录}/{date}_{标题}.md
        子目录：租房置业 / 消费选品 / 其他生活
    {vault}/阅读笔记/YYYY-MM/{date}_{书名}.md
    {vault}/语音备忘/YYYY-MM/{date}_语音备忘_{HHMMSS}.md
    {vault}/收藏夹/YYYY-MM/{date}_{标题}.md   ← 兜底，无法分类的内容
    {vault}/其他笔记/YYYY-MM/{date}_{标题}.md  ← 系统笔记等
"""
import re
from pathlib import Path
from datetime import datetime, timezone

from .config import config
from .parser import (
    ParsedNote,
    NOTE_TYPE_PODCAST, NOTE_TYPE_VOICE,
    NOTE_TYPE_ARTICLE, NOTE_TYPE_BOOK, NOTE_TYPE_WORK, NOTE_TYPE_UNKNOWN,
)

# 类型 → 目录名映射（兜底用，主要路由逻辑在 get_output_path）
_TYPE_DIR = {
    NOTE_TYPE_PODCAST: "播客笔记",
    NOTE_TYPE_VOICE:   "语音备忘",
    NOTE_TYPE_ARTICLE: "收藏夹",
    NOTE_TYPE_BOOK:    "阅读笔记",
    NOTE_TYPE_WORK:    "工作笔记",
    NOTE_TYPE_UNKNOWN: "其他笔记",
}

# ────────────────────────────────────────────────────────
# 播客主题子目录路由
# 匹配规则：tags 或 title 含以下关键词 → 分入对应子目录
# 未命中任何规则 → 其他播客
# 注：文章类内容如果命中了主题关键词，也会路由到此处（跨媒介合并）
# ────────────────────────────────────────────────────────
_PODCAST_TOPIC_RULES = [
    # (子目录名, {关键词集合})
    ("AI与科技",  {"ai", "人工智能", "科技", "技术", "kimi", "gpt", "llm", "大模型",
                   "认知", "算法", "深度学习", "机器学习", "ai认知", "ai时代",
                   "obsidian", "知识管理", "笔记工具"}),
    ("自我成长",  {"成长", "自我", "心理", "习惯", "效率", "人生", "女性", "社交",
                   "情绪", "精力", "复利", "学习", "认知升级", "个人发展", "改变"}),
    ("财商投资",  {"财富", "投资", "金融", "理财", "股票", "基金", "资产", "钱",
                   "财商", "经济", "商业", "创业", "纳瓦尔", "杠杆", "财务自由"}),
]
_PODCAST_DEFAULT_SUBDIR = "其他播客"

# ────────────────────────────────────────────────────────
# 旅行地区路由
# 匹配规则：tags 或 title 含地区关键词 → 分入 旅行/{地区}/
# 地区词本身即旅游触发词（无需单独维护通用旅游词）
# ────────────────────────────────────────────────────────
_TRAVEL_REGION_RULES = [
    # (地区目录名, {关键词集合})
    ("日本",  {"日本", "japan", "京都", "大阪", "东京", "奈良", "神户", "福冈",
               "北海道", "冲绳", "关西", "关东", "日式", "岚山", "祇园"}),
    ("东南亚", {"东南亚", "泰国", "曼谷", "清迈", "越南", "河内", "胡志明", "新加坡",
                "马来西亚", "吉隆坡", "巴厘岛", "印尼", "菲律宾", "柬埔寨"}),
    ("欧洲",  {"欧洲", "法国", "巴黎", "英国", "伦敦", "意大利", "罗马", "德国",
               "西班牙", "葡萄牙", "荷兰", "瑞士", "北欧", "希腊"}),
    ("港澳台", {"香港", "澳门", "台湾", "台北", "高雄", "台中"}),
    ("国内",  {"北京", "上海", "广州", "深圳", "成都", "杭州", "西安", "云南",
               "四川", "新疆", "西藏", "海南", "厦门", "重庆", "武汉", "苏州"}),
    ("美洲",  {"美国", "纽约", "洛杉矶", "旧金山", "加拿大", "多伦多",
               "墨西哥", "巴西", "阿根廷"}),
]

# ────────────────────────────────────────────────────────
# 生活决策子目录路由
# 匹配规则：tags 或 title 含以下关键词 → 分入 生活决策/{子目录}/
# ────────────────────────────────────────────────────────
_LIFE_TOPIC_RULES = [
    # (子目录名, {关键词集合})
    ("租房置业", {"租房", "看房", "房源", "小区", "公寓", "合租", "房租",
                  "买房", "房产", "装修", "选房", "中介", "租约", "安居"}),
    ("消费选品", {"测评", "推荐", "好物", "选购", "开箱", "种草",
                  "购物", "清单", "评测", "性价比", "值不值得买", "好用", "避坑"}),
]
_LIFE_DEFAULT_SUBDIR = "其他生活"


class ObsidianRenderer:
    def __init__(self, vault_path: Path = None):
        self.vault = vault_path or config.obsidian_vault

    # ────────────────────────────────────────────────
    # 公开接口
    # ────────────────────────────────────────────────

    def get_output_path(self, note: ParsedNote) -> Path:
        """
        计算目标文件路径（不创建文件）。

        路由优先级（按内容主题域，不按来源媒介）：
        1. 播客   → 播客笔记/{主题子目录}/
        2. 工作   → 工作笔记/
        3. 文章   → 多层路由（优先级从高到低）：
              a. 命中主题关键词（AI/成长/财商）→ 播客笔记/{主题子目录}/（跨媒介合并）
              b. 命中生活决策关键词            → 生活决策/{子目录}/（优先于旅行，防止「深圳租房」误判）
              c. 命中地区关键词               → 旅行/{地区}/
              d. 兜底                         → 收藏夹/YYYY-MM/
        4. 读书   → 阅读笔记/YYYY-MM/
        5. 语音   → 语音备忘/YYYY-MM/
        6. 其他   → 其他笔记/YYYY-MM/（系统笔记等）
        """
        filename = self._make_filename(note)

        # ── 播客笔记：按主题子目录分类 ──────────────────────
        if note.note_type == NOTE_TYPE_PODCAST:
            subdir = _classify_podcast_topic(note)
            return self.vault / "播客笔记" / subdir / filename

        # ── 工作笔记：顶层工作笔记/，不分月份 ───────────────
        if note.note_type == NOTE_TYPE_WORK:
            return self.vault / "工作笔记" / filename

        # ── 文章剪藏：多层路由，按内容主题而非来源媒介 ───────
        if note.note_type == NOTE_TYPE_ARTICLE:
            # a. 命中主题关键词 → 与播客内容合并（如 AI 文章进 AI与科技/）
            topic_subdir = _classify_podcast_topic(note)
            if topic_subdir != _PODCAST_DEFAULT_SUBDIR:
                return self.vault / "播客笔记" / topic_subdir / filename
            # b. 命中生活决策关键词 → 生活决策/{子目录}/（优先于旅行，避免「深圳租房」误判为旅行）
            life_subdir = _classify_life_topic(note)
            if life_subdir:
                return self.vault / "生活决策" / life_subdir / filename
            # c. 命中地区关键词 → 旅行/{地区}/
            region = _classify_travel_region(note)
            if region:
                return self.vault / "旅行" / region / filename
            # d. 兜底
            return self.vault / "收藏夹" / note.created_month / filename

        # ── 读书笔记：阅读笔记/YYYY-MM/ ─────────────────────
        if note.note_type == NOTE_TYPE_BOOK:
            return self.vault / "阅读笔记" / note.created_month / filename

        # ── 语音备忘：语音备忘/YYYY-MM/ ─────────────────────
        if note.note_type == NOTE_TYPE_VOICE:
            return self.vault / "语音备忘" / note.created_month / filename

        # ── 其他（系统笔记等）────────────────────────────────
        return self.vault / "其他笔记" / note.created_month / filename

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

    def write(self, note: ParsedNote, dry_run: bool = False) -> Path:
        """
        渲染并写入文件。

        参数：
            dry_run: True 时只打印路径，不实际写入

        返回：
            目标文件路径
        """
        output_path = self.get_output_path(note)

        if dry_run:
            print(f"  [dry-run] → {output_path}")
            return output_path

        # 目录不存在则创建
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 已存在则跳过（防重保险）
        if output_path.exists():
            return output_path

        content = self.render(note)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path

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

        # 语音备忘通常内容单一，不加目录
        if note.transcript:
            lines += ["", "## 🎙 转写内容", "", note.transcript, ""]
        elif note.body_text:
            lines += ["", "## 🎙 内容", "", note.body_text, ""]

        if note.summary:
            lines += ["", "## 📝 AI 整理", "", note.summary, ""]

        if note.quotes:
            lines += ["", "## 💬 重点摘录", ""]
            for q in note.quotes:
                lines += [f"> {q}", ""]

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
        - 播客/文章/读书/工作：{来源}_{标题}_{date}.md
        - 语音备忘：语音备忘_{HHMMSS}_{date}.md
        """
        date = note.created_date  # 2026-03-15

        if note.note_type == NOTE_TYPE_VOICE:
            time_part = note.created_time_str
            return f"语音备忘_{time_part}_{date}.md"

        parts = []
        if note.source_name:
            parts.append(_sanitize(note.source_name, max_len=20))
        if note.title:
            title_clean = _sanitize(note.title, max_len=40)
            if title_clean and title_clean != _sanitize(note.source_name or "", max_len=20):
                parts.append(title_clean)
        parts.append(date)

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


def _classify_podcast_topic(note: ParsedNote) -> str:
    """
    根据笔记的 tags + title，返回主题子目录名。
    适用于播客笔记，以及路由到播客目录的文章笔记。

    匹配优先级：按 _PODCAST_TOPIC_RULES 顺序（AI与科技 > 自我成长 > 财商投资），
    未命中则返回默认子目录「其他播客」。
    """
    tags_lower = {t.lower() for t in note.tags}
    title_lower = (note.title or "").lower()

    for subdir, keywords in _PODCAST_TOPIC_RULES:
        for kw in keywords:
            if kw in tags_lower or kw in title_lower:
                return subdir
    return _PODCAST_DEFAULT_SUBDIR


def _classify_travel_region(note: ParsedNote) -> str:
    """
    判断文章是否属于旅行类，若是则返回地区目录名，否则返回空字符串。

    匹配逻辑：tags 或 title 含任意地区关键词 → 视为旅行类并返回地区名。
    未命中任何地区但含通用旅游词（旅游/旅行/攻略）→ 返回「其他目的地」。
    """
    tags_lower = {t.lower() for t in note.tags}
    title_lower = (note.title or "").lower()

    for region, keywords in _TRAVEL_REGION_RULES:
        for kw in keywords:
            if kw in tags_lower or kw in title_lower:
                return region

    # 含通用旅游词但未命中具体地区
    _GENERAL_TRAVEL = {"旅游", "旅行", "攻略", "出行", "自由行", "深度游", "景点", "酒店"}
    if any(kw in tags_lower or kw in title_lower for kw in _GENERAL_TRAVEL):
        return "其他目的地"

    return ""


def _classify_life_topic(note: ParsedNote) -> str:
    """
    判断文章是否属于生活决策类，若是则返回子目录名，否则返回空字符串。

    匹配规则：tags 或 title 含 _LIFE_TOPIC_RULES 中的关键词 → 对应子目录。
    未命中任何规则 → 返回空字符串（不强制归入生活决策）。
    """
    tags_lower = {t.lower() for t in note.tags}
    title_lower = (note.title or "").lower()

    for subdir, keywords in _LIFE_TOPIC_RULES:
        for kw in keywords:
            if kw in tags_lower or kw in title_lower:
                return subdir
    return ""


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 字符串"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _quote_line(text: str) -> str:
    """生成 Markdown 引用格式的金句行（兼容 Python 3.9）"""
    return "> \u201c" + text + "\u201d"

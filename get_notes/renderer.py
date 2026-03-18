"""
renderer.py — 输出 Obsidian Markdown

根据笔记类型选择对应模板，生成 Markdown 文件并写入 Obsidian Vault。

目录结构：
    {vault}/播客笔记/YYYY-MM/{date}_{来源}_{标题}.md
    {vault}/语音备忘/YYYY-MM/{date}_语音备忘_{HHMMSS}.md
    {vault}/文章剪藏/YYYY-MM/{date}_{标题}.md
    {vault}/读书笔记/YYYY-MM/{date}_{书名}.md
    {vault}/工作笔记/YYYY-MM/{date}_{标题}.md
    {vault}/其他笔记/YYYY-MM/{date}_{标题}.md
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

# 类型 → 目录名映射
_TYPE_DIR = {
    NOTE_TYPE_PODCAST: "播客笔记",
    NOTE_TYPE_VOICE:   "语音备忘",
    NOTE_TYPE_ARTICLE: "文章剪藏",
    NOTE_TYPE_BOOK:    "读书笔记",
    NOTE_TYPE_WORK:    "工作笔记",
    NOTE_TYPE_UNKNOWN: "其他笔记",
}


class ObsidianRenderer:
    def __init__(self, vault_path: Path = None):
        self.vault = vault_path or config.obsidian_vault

    # ────────────────────────────────────────────────
    # 公开接口
    # ────────────────────────────────────────────────

    def get_output_path(self, note: ParsedNote) -> Path:
        """计算目标文件路径（不创建文件）"""
        type_dir = _TYPE_DIR.get(note.note_type, "其他笔记")
        month_dir = note.created_month  # 如 "2026-03"
        filename  = self._make_filename(note)
        return self.vault / type_dir / month_dir / filename

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
            sections.append(("📄 原文内容", "📄-原文内容"))

        lines += _toc(sections)

        if note.summary:
            lines += ["", "## 📝 我的笔记 / AI 总结", "", note.summary, ""]

        if note.quotes:
            lines += ["", "## 💬 划线金句", ""]
            for q in note.quotes:
                lines += [_quote_line(q), ""]

        if note.body_text:
            lines += ["", "## 📄 原文内容", "", note.body_text, ""]

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


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 字符串"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _quote_line(text: str) -> str:
    """生成 Markdown 引用格式的金句行（兼容 Python 3.9）"""
    return "> \u201c" + text + "\u201d"

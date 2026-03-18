"""
parser.py — 笔记类型识别 + 内容结构化

将原始 API 数据 → 结构化的 ParsedNote 对象，
统一字段命名，屏蔽 API 数据的不一致性。
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ────────────────────────────────────────────────────────
# 类型常量
# ────────────────────────────────────────────────────────

NOTE_TYPE_PODCAST = "podcast"    # 播客/音频转写（小宇宙、喜马拉雅等）
NOTE_TYPE_VOICE   = "voice"      # 个人语音备忘
NOTE_TYPE_ARTICLE = "article"    # 文章/网页剪藏（小红书等）
NOTE_TYPE_BOOK    = "book"       # 读书笔记
NOTE_TYPE_WORK    = "work"       # 工作笔记（答辩、项目、职场相关）
NOTE_TYPE_UNKNOWN = "unknown"    # 无法识别

# 播客平台 URL 域名关键词（优先级最高，基于真实 URL 匹配）
_PODCAST_URL_DOMAINS = {
    "xiaoyuzhoufm.com",      # 小宇宙
    "ximalaya.com",          # 喜马拉雅
    "spotify.com",
    "podcasts.apple.com",
    "podcasts.google.com",
    "podbean.com",
    "lizhi.fm",              # 荔枝
    "dedao.cn",              # 得到
    "qingting.fm",           # 蜻蜓
}

# 播客平台名称关键词（source_name 匹配，宽松）
_PODCAST_PLATFORMS = {
    "小宇宙", "喜马拉雅", "spotify", "apple podcast", "podcast",
    "podcasts", "podbean", "lizhi", "荔枝", "得到", "蜻蜓",
    "喜马", "网易云音乐", "bilibili", "b站", "youtube",
}

# 小红书 URL 特征
_XIAOHONGSHU_URL_DOMAINS = {
    "xhslink.com",
    "xiaohongshu.com",
    "xhs.cn",
}

# 书籍相关关键词（用于识别读书笔记）
_BOOK_TAGS = {"reading", "book", "读书", "书", "笔记", "阅读"}

# 工作笔记关键词（tags 或 title 包含这些词时归入工作笔记）
# 可根据自己的工作场景自由扩充
_WORK_TAGS = {"工作", "work", "职场", "答辩", "晋升", "项目", "汇报", "okr", "kpi",
              "会议", "meeting", "周报", "月报", "复盘"}

# Get 笔记平台自身的介绍文章黑名单（note_id）
# 使用 --full-sync 后，如发现某些系统预置笔记不想同步，
# 可将其 note_id 字符串加入此处，之后的同步将自动跳过。
# 示例：
#   "1894909191618305632",   # Hi，欢迎来到Get笔记
#   "1894909191617781344",   # Get笔记2.0：你好，我是你的AI助手
BLOCKED_NOTE_IDS: set[str] = set()


# ────────────────────────────────────────────────────────
# 数据结构
# ────────────────────────────────────────────────────────

@dataclass
class Chapter:
    """重点章节"""
    timestamp: str   # 如 "00:15:44"
    title: str
    content: str


@dataclass
class ParsedNote:
    # 元数据
    id: str
    title: str
    note_type: str          # podcast / voice / article / book / unknown
    created_at: str         # ISO 8601 字符串，如 "2026-03-15T10:30:00Z"
    updated_at: str

    # 来源信息
    source_url: Optional[str] = None
    source_name: Optional[str] = None   # 平台/播客名称

    # 内容
    summary: Optional[str] = None           # AI 生成的总结
    transcript: Optional[str] = None        # 原始转写（带时间戳）
    body_text: Optional[str] = None         # 正文/笔记内容
    chapters: list[Chapter] = field(default_factory=list)
    quotes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    # 辅助字段
    duration_sec: int = 0                   # 音频时长（秒）
    audio_url: Optional[str] = None
    raw: dict = field(default_factory=dict, repr=False)  # 保留原始数据

    @property
    def created_date(self) -> str:
        """返回日期字符串，如 2026-03-15"""
        if not self.created_at:
            return "unknown"
        # 支持 "2026-03-15 14:13:05" 和 "2026-03-15T10:30:00Z" 两种格式
        try:
            ts = self.created_at.replace("Z", "+00:00").replace(" ", "T")
            dt = datetime.fromisoformat(ts)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            return self.created_at[:10] if self.created_at else "unknown"

    @property
    def created_month(self) -> str:
        """返回年月字符串，如 2026-03"""
        return self.created_date[:7]

    @property
    def created_time_str(self) -> str:
        """返回时间字符串，如 143521（用于语音备忘文件名）"""
        try:
            ts = self.created_at.replace("Z", "+00:00").replace(" ", "T")
            dt = datetime.fromisoformat(ts)
            return dt.strftime("%H%M%S")
        except (ValueError, AttributeError):
            return "000000"

    @property
    def duration_display(self) -> str:
        """返回可读的时长，如 '52min' 或 '1h30min'"""
        if not self.duration_sec:
            return ""
        minutes = self.duration_sec // 60
        if minutes < 60:
            return f"{minutes}min"
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h{mins}min" if mins else f"{hours}h"


# ────────────────────────────────────────────────────────
# 解析函数
# ────────────────────────────────────────────────────────

def parse_note(raw: dict) -> ParsedNote:
    """
    将原始 API 数据转成 ParsedNote 对象。

    API 数据来自 fetcher.fetch_note_with_detail() 的合并结果，
    包含列表字段、详情字段和 _original（原始转写）。
    """
    note_id  = raw.get("note_id") or raw.get("id", "")
    title    = _extract_title(raw)
    tags     = [t.get("name", "") for t in raw.get("tags", []) if t.get("name")]
    src_url  = _extract_source_url(raw)
    src_name = _extract_source_name(raw)
    note_type = detect_note_type(raw, src_url, src_name, tags)

    # 内容字段
    summary    = _extract_summary(raw)
    chapters   = _extract_chapters(raw)
    quotes     = _extract_quotes(raw)
    transcript = _extract_transcript(raw)
    body_text  = _extract_body(raw)

    return ParsedNote(
        id=note_id,
        title=title or _default_title(raw),
        note_type=note_type,
        created_at=raw.get("created_at") or raw.get("date_str", ""),
        updated_at=raw.get("edit_time") or raw.get("updated_at") or raw.get("date_str", ""),
        source_url=src_url,
        source_name=src_name,
        summary=summary,
        transcript=transcript,
        body_text=body_text,
        chapters=chapters,
        quotes=quotes,
        tags=tags,
        duration_sec=int(raw.get("duration", 0) or 0),
        audio_url=raw.get("audio_url"),
        raw=raw,
    )


def detect_note_type(
    raw: dict,
    src_url: Optional[str] = None,
    src_name: Optional[str] = None,
    tags: Optional[list] = None,
) -> str:
    """
    识别笔记类型，基于真实 API 字段 note_type + URL 域名 + 标签。

    Get笔记真实 note_type 值：
    - "local_audio"  → 本地上传音频（播客录音等） → podcast
    - "audio"        → 录音/语音备忘              → voice
    - "link"         → 链接/文章剪藏              → podcast/article/work
    - "img_text"     → 图文笔记                   → book/article/work
    - "plain_text"   → 纯文字笔记                 → unknown
    """
    tags = tags or []
    tags_lower = {t.lower() for t in tags}
    api_note_type = (raw.get("note_type") or "").lower()
    src_url_lower  = (src_url or "").lower()
    src_name_lower = (src_name or "").lower()
    title_lower    = (raw.get("title") or "").lower()

    # 1. 本地上传音频 → 播客
    if api_note_type == "local_audio":
        return NOTE_TYPE_PODCAST

    # 2. 录音 → 语音备忘
    if api_note_type == "audio":
        return NOTE_TYPE_VOICE

    # 3. 链接笔记 / 图文笔记 — 按优先级判断
    if api_note_type in ("link", "img_text", ""):
        # 3a. URL 域名匹配播客平台（最高优先级，精确）
        for domain in _PODCAST_URL_DOMAINS:
            if domain in src_url_lower:
                return NOTE_TYPE_PODCAST

        # 3b. 工作笔记识别：tags 或 title 含工作关键词
        if tags_lower & _WORK_TAGS:
            return NOTE_TYPE_WORK
        if any(kw in title_lower for kw in _WORK_TAGS):
            return NOTE_TYPE_WORK

        # 3c. 读书笔记识别（img_text 为主）
        if api_note_type == "img_text":
            if tags_lower & _BOOK_TAGS:
                return NOTE_TYPE_BOOK
            if "读书" in title_lower or "阅读" in title_lower:
                return NOTE_TYPE_BOOK

        # 3d. 来源名称匹配播客关键词（宽松匹配）
        for keyword in _PODCAST_PLATFORMS:
            if keyword.lower() in src_name_lower or keyword.lower() in src_url_lower:
                return NOTE_TYPE_PODCAST

        # 3e. 默认为文章
        return NOTE_TYPE_ARTICLE

    return NOTE_TYPE_UNKNOWN


# ────────────────────────────────────────────────────────
# 字段提取辅助函数
# ────────────────────────────────────────────────────────

def _extract_title(raw: dict) -> str:
    return (raw.get("title") or "").strip()


def _default_title(raw: dict) -> str:
    """当 title 为空时，用时间生成默认标题"""
    created = raw.get("created_at", "")[:10]
    return f"无标题笔记 {created}"


def _extract_source_url(raw: dict) -> Optional[str]:
    """从多个可能的字段中提取来源 URL"""
    # 直接字段
    url = raw.get("source_url") or raw.get("url")
    if url:
        return url
    # res_info 对象（Get笔记真实结构）
    res_info = raw.get("res_info") or {}
    if isinstance(res_info, dict):
        u = res_info.get("url") or res_info.get("link")
        if u:
            return u
    # 附件中的第一个链接
    attachments = raw.get("attachments") or []
    for att in attachments:
        if isinstance(att, dict) and att.get("type") == "link" and att.get("url"):
            return att["url"]
    # source 对象（只有当 source 是 dict 时才取）
    source = raw.get("source")
    if isinstance(source, dict):
        return source.get("url") or source.get("link")
    return None


def _extract_source_name(raw: dict) -> Optional[str]:
    """提取来源平台/播客名称"""
    # res_info 对象（Get笔记真实结构）
    res_info = raw.get("res_info") or {}
    if isinstance(res_info, dict):
        name = res_info.get("title") or res_info.get("ptype_cn_name")
        if name and name.strip():
            return name.strip()
    # source 只有当它是 dict 时才取
    source = raw.get("source")
    if isinstance(source, dict):
        name = source.get("name") or source.get("platform")
        if name:
            return name.strip()
    # 其他可能字段
    for key in ("source_name", "program_name", "podcast_name"):
        val = raw.get(key)
        if val and isinstance(val, str):
            return val.strip()
    return None


def _extract_summary(raw: dict) -> Optional[str]:
    """提取 AI 总结"""
    for key in ("summary", "ai_summary", "abstract", "brief"):
        val = raw.get(key)
        if val and isinstance(val, str):
            return val.strip()
    # content 只有当它是 dict 时才查子字段
    content = raw.get("content")
    if isinstance(content, dict):
        return content.get("summary")
    return None


def _extract_chapters(raw: dict) -> list[Chapter]:
    """提取重点章节列表"""
    content = raw.get("content")
    content_chapters = content.get("chapters") if isinstance(content, dict) else []
    chapters_raw = (
        raw.get("chapters")
        or raw.get("key_chapters")
        or content_chapters
        or []
    )
    result = []
    for ch in chapters_raw:
        if not isinstance(ch, dict):
            continue
        result.append(Chapter(
            timestamp=ch.get("timestamp") or ch.get("time") or "",
            title=ch.get("title") or ch.get("name") or "",
            content=ch.get("content") or ch.get("summary") or "",
        ))
    return result


def _extract_quotes(raw: dict) -> list[str]:
    """提取金句列表"""
    content = raw.get("content")
    content_quotes = content.get("quotes") if isinstance(content, dict) else []
    quotes_raw = (
        raw.get("quotes")
        or raw.get("key_quotes")
        or raw.get("highlights")
        or content_quotes
        or []
    )
    result = []
    for q in quotes_raw:
        if isinstance(q, str) and q.strip():
            result.append(q.strip())
        elif isinstance(q, dict):
            text = q.get("text") or q.get("content") or q.get("quote") or ""
            if text.strip():
                result.append(text.strip())
    return result


def _extract_transcript(raw: dict) -> Optional[str]:
    """
    提取原始转写内容（带时间戳）。
    来源：_original 字段（由 fetcher 注入）
    """
    original = raw.get("_original")
    if not original:
        return None
    if isinstance(original, str):
        return original.strip()
    if isinstance(original, dict):
        # 常见格式：{ "text": "...", "segments": [...] }
        if original.get("text"):
            return original["text"].strip()
        # 逐段拼接
        segments = original.get("segments") or original.get("transcript") or []
        if segments:
            lines = []
            for seg in segments:
                ts = seg.get("timestamp") or seg.get("start_time") or ""
                text = seg.get("text") or seg.get("content") or ""
                if ts and text:
                    lines.append(f"`[{ts}]` {text}")
                elif text:
                    lines.append(text)
            return "\n".join(lines)
    return None


def _extract_body(raw: dict) -> Optional[str]:
    """
    提取笔记正文。
    优先取 content（完整 Markdown，Get笔记的主要内容字段），
    其次取 body_text（纯文本摘要，通常被截断，不完整）。
    """
    # 优先：content 字段（完整 Markdown 内容）
    content = raw.get("content")
    if isinstance(content, str) and content.strip():
        # content 本身已经是 Markdown，直接使用
        return content.strip()

    # 备选：note_content
    note_content = raw.get("note_content")
    if note_content and isinstance(note_content, str):
        return note_content.strip()

    # 最后兜底：body_text（纯文本，可能截断，转换 HTML 换行）
    body = raw.get("body_text")
    if body and isinstance(body, str):
        text = re.sub(r"<br\s*/?>", "\n", body)   # <br> → 换行
        text = re.sub(r"<[^>]+>", "", text)         # 清除其他 HTML 标签
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    return None

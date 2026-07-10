"""
diary_writer.py — 语音备忘自动写入日记流水账

当语音备忘同步完成后，将其 ## 📝 笔记内容 写入 Going Dairy 对应日期的 ## 流水账。
只写入空的流水账，已有内容的条目自动跳过。
"""
import time
from pathlib import Path

from .parser import ParsedNote, NOTE_TYPE_VOICE
from .renderer import _voice_diary_date


# 返回状态常量
STATUS_WRITTEN  = "written"   # 成功写入
STATUS_SKIPPED  = "skipped"   # 流水账已有内容，跳过
STATUS_NO_DIARY = "no_diary"  # 日记文件不存在
STATUS_NO_NOTES = "no_notes"  # 语音备忘无笔记内容（body_text 为空）
STATUS_ERROR    = "error"     # 读写异常


def _safe_read(path: Path, retries: int = 3):
    """读取文件内容，iCloud 延迟加载时自动重试。返回 (content, error)。"""
    for attempt in range(retries):
        try:
            return path.read_text(encoding="utf-8"), None
        except OSError as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                return None, str(e)


def _safe_write(path: Path, content: str, retries: int = 3):
    """写入文件，失败时自动重试。返回 (ok, error)。"""
    for attempt in range(retries):
        try:
            path.write_text(content, encoding="utf-8")
            return True, None
        except OSError as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                return False, str(e)


def _extract_section(content: str, section_title: str) -> str:
    """提取某个 ## 节的正文（到下一个 ## 为止）。"""
    if section_title not in content:
        return ""
    after = content.split(section_title, 1)[1]
    lines = after.split("\n")
    body_lines = []
    for line in lines[1:]:
        if line.startswith("## "):
            break
        body_lines.append(line)
    return "\n".join(body_lines).strip()


def _insert_liushui(diary_content: str, notes_content: str):
    """
    将 notes_content 插入日记的 ## 流水账 节（节内容为空时才插入）。
    返回 (new_content, status)。
    """
    marker = "## 流水账"
    if marker not in diary_content:
        return None, "NO_SECTION"

    before, rest = diary_content.split(marker, 1)
    lines = rest.split("\n")

    # 找下一个 ## 节的位置
    next_idx = None
    for i, line in enumerate(lines[1:], 1):
        if line.startswith("## "):
            next_idx = i
            break

    if next_idx is not None:
        after = "\n".join(lines[next_idx:])
        new_content = before + marker + "\n\n" + notes_content + "\n\n" + after
    else:
        new_content = before + marker + "\n\n" + notes_content + "\n"

    return new_content, "OK"


class DiaryWriter:
    """
    同步语音备忘后，将笔记内容写入对应日期的日记流水账。

    参数：
        diary_daily_path: Going Dairy daily 目录的路径
            默认从 vault 路径推导：vault.parent / "Going Dairy" / "daily"
    """

    def __init__(self, vault_path: Path):
        self.diary_base = vault_path.parent / "Going Dairy" / "daily"

    def write_to_diary(
        self,
        note: ParsedNote,
        dry_run: bool = False,
    ) -> tuple[str, str]:
        """
        将语音备忘的笔记内容写入对应日记的流水账。

        返回：
            (status, message) — status 为上方 STATUS_* 常量之一
        """
        if note.note_type != NOTE_TYPE_VOICE:
            return STATUS_ERROR, "不是语音备忘类型"

        # 笔记内容
        notes_content = (note.body_text or "").strip()
        if not notes_content:
            return STATUS_NO_NOTES, "语音备忘无笔记内容（body_text 为空）"

        # 日记路径
        diary_date = _voice_diary_date(note)  # 已处理凌晨录音归前一天
        ym = diary_date[:7]
        diary_path = self.diary_base / ym / f"{diary_date}.md"

        if not diary_path.exists():
            return STATUS_NO_DIARY, f"日记文件不存在：{diary_path.name}"

        # 读取日记
        content, err = _safe_read(diary_path)
        if content is None:
            return STATUS_ERROR, f"读取日记失败：{err}"

        # 流水账已有内容 → 跳过
        current = _extract_section(content, "## 流水账")
        if current:
            return STATUS_SKIPPED, f"流水账已有内容（{len(current)}字），跳过"

        # dry-run 模式
        if dry_run:
            return STATUS_WRITTEN, f"[dry-run] 将写入 {diary_path.name}（{len(notes_content)}字）"

        # 插入内容
        new_content, insert_status = _insert_liushui(content, notes_content)
        if insert_status != "OK":
            return STATUS_ERROR, f"日记缺少流水账节（{insert_status}）"

        ok, err = _safe_write(diary_path, new_content)
        if not ok:
            return STATUS_ERROR, f"写入失败：{err}"

        return STATUS_WRITTEN, f"已写入 {diary_path.name}（{len(notes_content)}字）"

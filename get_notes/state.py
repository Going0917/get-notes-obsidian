"""
state.py — 增量同步状态管理

读写 .sync_state.json，记录上次同步位置，
确保每次运行只拉取新增内容。
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import config


class SyncState:
    def __init__(self):
        self.state_file: Path = config.state_file
        self._data: dict = self._load()

    # ────────────────────────────────────────────────
    # 公开接口
    # ────────────────────────────────────────────────

    def get_last_synced_id(self) -> Optional[str]:
        """返回上次同步的最新笔记 ID（用于增量游标）"""
        return self._data.get("last_synced_note_id")

    def get_synced_ids(self) -> set:
        """返回已同步的笔记 ID 集合（用于防重复）"""
        return set(self._data.get("synced_ids", []))

    def update(self, latest_note_id: str, new_ids: list[str]):
        """
        同步完成后更新状态

        参数：
            latest_note_id: 本次同步的最新笔记 ID（按创建时间排序的最新一条）
            new_ids:        本次新同步的所有笔记 ID 列表
        """
        existing_ids = set(self._data.get("synced_ids", []))
        existing_ids.update(new_ids)

        self._data["last_synced_note_id"] = latest_note_id
        self._data["last_synced_at"] = datetime.now().isoformat(timespec="seconds")
        self._data["total_synced"] = self._data.get("total_synced", 0) + len(new_ids)
        # 只保留最近 2000 条 ID，防止文件无限膨胀
        self._data["synced_ids"] = list(existing_ids)[-2000:]
        self._save()

    def reset(self):
        """清空状态（供 --full-sync 模式使用）"""
        self._data = {}
        if self.state_file.exists():
            self.state_file.unlink()

    def summary(self) -> str:
        """返回当前同步状态的简短描述"""
        total = self._data.get("total_synced", 0)
        last_at = self._data.get("last_synced_at", "从未同步")
        return f"历史累计同步 {total} 条，上次同步时间：{last_at}"

    # ────────────────────────────────────────────────
    # 私有方法
    # ────────────────────────────────────────────────

    def _load(self) -> dict:
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def _save(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

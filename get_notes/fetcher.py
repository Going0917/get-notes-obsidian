"""
fetcher.py — 数据拉取（分页 + 增量控制）

支持两种模式：
- fetch_incremental(): 增量拉取，遇到上次同步位置停止
- fetch_all():         全量拉取（--full-sync 模式）

每条笔记自动附加完整内容（detail + original 转写）
"""
from __future__ import annotations
from typing import Optional

from .client import GetNotesClient
from .config import config


class GetNotesFetcher:
    def __init__(self, client: GetNotesClient):
        self.client = client
        self.limit = config.sync_limit

    # ────────────────────────────────────────────────
    # 公开接口
    # ────────────────────────────────────────────────

    def fetch_incremental(
        self,
        last_synced_id: Optional[str],
        synced_ids: Optional[set] = None,
        note_type_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        增量拉取：从最新往前，遇到 last_synced_id 停止。

        参数：
            last_synced_id:   上次同步的最新笔记 ID（来自 SyncState）
            synced_ids:       已同步 ID 集合，用于防重
            note_type_filter: 可选，只拉取特定类型（原始 API 的 entry_type 字段）

        返回：
            按创建时间从旧到新排序的笔记列表（不含 last_synced_id 本身）
        """
        synced_ids = synced_ids or set()
        new_notes = []
        since_id = None
        reached_last = False

        print(f"🔍 开始增量拉取（上次位置：{last_synced_id or '无，首次全量'}）")

        while True:
            page = self.client.get_notes_list(
                limit=self.limit,
                since_id=since_id,
            )
            notes = page.get("list", [])

            if not notes:
                break

            for note in notes:
                note_id = note.get("note_id") or note.get("id")

                # 遇到上次同步的边界，停止
                if last_synced_id and note_id == last_synced_id:
                    reached_last = True
                    break

                # 跳过已同步的（防重保险）
                if note_id in synced_ids:
                    continue

                new_notes.append(note)

            if reached_last or not page.get("has_more", False):
                break

            # 游标：本页最后一条的 ID
            last_note = notes[-1]
            since_id = last_note.get("note_id") or last_note.get("id")

        # 按创建时间从旧到新排序（保证写入顺序一致）
        new_notes.sort(key=lambda n: n.get("created_at", ""))

        print(f"📋 找到 {len(new_notes)} 条新笔记，开始拉取详情...")
        return new_notes

    def fetch_all(self) -> list[dict]:
        """
        全量拉取所有笔记（用于 --full-sync 模式）
        """
        all_notes = []
        since_id = None

        print("🔍 开始全量拉取...")

        while True:
            page = self.client.get_notes_list(limit=self.limit, since_id=since_id)
            notes = page.get("list", [])

            if not notes:
                break

            all_notes.extend(notes)
            total = page.get("total_items", "?")
            print(f"  已拉取 {len(all_notes)} / {total} 条...")

            if not page.get("has_more", False):
                break

            last_note = notes[-1]
            since_id = last_note.get("note_id") or last_note.get("id")

        # 按创建时间从旧到新排序
        all_notes.sort(key=lambda n: n.get("created_at", ""))
        print(f"📋 全量拉取完成，共 {len(all_notes)} 条，开始拉取详情...")
        return all_notes

    def fetch_note_with_detail(self, note: dict) -> dict:
        """
        拉取单条笔记的完整内容：
        - detail:   笔记详情（包含 content、summary、chapters、quotes 等）
        - original: 原始转写（带时间戳的逐字稿）

        将所有字段合并到 note dict 中返回。
        """
        note_id = note.get("note_id") or note.get("id")

        # 拉取详情
        try:
            detail = self.client.get_note_detail(note_id)
            # 合并详情字段（不覆盖列表接口已有的字段）
            for k, v in detail.items():
                if k not in note or not note[k]:
                    note[k] = v
        except Exception as e:
            print(f"  ⚠️  详情拉取失败（{note_id}）：{e}")

        # 拉取原始转写（只有音频类笔记才有）
        if note.get("audio_url") or note.get("raw_status") == "done":
            try:
                original = self.client.get_note_original(note_id)
                note["_original"] = original
            except Exception as e:
                print(f"  ⚠️  原始转写拉取失败（{note_id}）：{e}")
                note["_original"] = None
        else:
            note["_original"] = None

        return note

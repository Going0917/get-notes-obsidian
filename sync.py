#!/usr/bin/env python3
"""
sync.py — Get 笔记同步主入口

用法：
    python3 sync.py                  # 增量同步（默认）
    python3 sync.py --full-sync      # 全量重新同步
    python3 sync.py --dry-run        # 只打印，不写文件
    python3 sync.py --type podcast   # 只同步播客笔记
    python3 sync.py --limit 20       # 本次最多同步 N 条

完成后打印摘要：同步条数、类型分布、最新笔记标题。
"""
import argparse
import sys
import os
from collections import Counter
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

from get_notes.auth import GetNotesAuth
from get_notes.client import GetNotesClient
from get_notes.config import config
from get_notes.fetcher import GetNotesFetcher
from get_notes.parser import parse_note, BLOCKED_NOTE_IDS
from get_notes.renderer import ObsidianRenderer
from get_notes.state import SyncState


def main():
    parser = argparse.ArgumentParser(
        description="将 Get 笔记同步到 Obsidian Vault",
    )
    parser.add_argument(
        "--full-sync",
        action="store_true",
        help="全量重新同步（忽略增量状态）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印待同步列表，不写入文件",
    )
    parser.add_argument(
        "--type",
        choices=["podcast", "voice", "article", "book", "work"],
        help="只同步指定类型的笔记",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="本次最多同步 N 条（默认不限）",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("📥 Get 笔记同步工具")
    print("=" * 60)

    # ── 1. 初始化 ─────────────────────────────────────────────────
    state    = SyncState()
    renderer = ObsidianRenderer()

    print(f"📂 输出目录：{config.obsidian_vault}")
    print(f"📊 {state.summary()}")

    # ── 2. 获取 Token ──────────────────────────────────────────────
    auth  = GetNotesAuth()
    token = auth.get_token()

    # ── 3. 初始化 Client + Fetcher ────────────────────────────────
    client  = GetNotesClient(token)
    fetcher = GetNotesFetcher(client)

    # ── 4. 拉取笔记列表 ────────────────────────────────────────────
    if args.full_sync:
        print("\n⚠️  全量同步模式，将重新同步所有笔记")
        raw_notes = fetcher.fetch_all()
    else:
        last_id = state.get_last_synced_id()
        raw_notes = fetcher.fetch_incremental(
            last_synced_id=last_id,
            synced_ids=state.get_synced_ids(),
        )

    if not raw_notes:
        print("\n✅ 没有新笔记，已是最新状态。")
        return

    # 应用数量限制
    if args.limit:
        raw_notes = raw_notes[:args.limit]
        print(f"  （已应用 --limit {args.limit}，本次最多处理 {args.limit} 条）")

    print(f"\n🚀 开始同步 {len(raw_notes)} 条笔记...\n")

    # ── 5. 逐条拉取详情 + 解析 + 写入 ─────────────────────────────
    synced_ids   = []
    latest_note  = None
    type_counter = Counter()
    errors       = []

    for i, raw in enumerate(raw_notes, 1):
        note_id = raw.get("note_id") or raw.get("id", "?")
        try:
            # 黑名单过滤（Get 笔记平台介绍等无用内容）
            if str(note_id) in BLOCKED_NOTE_IDS:
                print(f"  ⏭  [{i}/{len(raw_notes)}] {note_id} 已跳过（黑名单）")
                synced_ids.append(note_id)  # 仍记入已处理，防止下次重复拉取
                continue

            # 拉取完整内容（detail + original）
            full_raw  = fetcher.fetch_note_with_detail(raw)
            note      = parse_note(full_raw)

            # 类型过滤
            if args.type and note.note_type != args.type:
                continue

            # 写入 Obsidian
            out_path = renderer.write(note, dry_run=args.dry_run)

            type_counter[note.note_type] += 1
            synced_ids.append(note_id)
            latest_note = note

            status = "[dry-run]" if args.dry_run else "✅"
            title_display = note.title[:40] + ("…" if len(note.title) > 40 else "")
            print(f"  {status} [{i}/{len(raw_notes)}] {note.note_type:8} | {note.created_date} | {title_display}")

        except Exception as e:
            errors.append((note_id, str(e)))
            print(f"  ❌ [{i}/{len(raw_notes)}] {note_id} 失败：{e}")

    # ── 6. 更新状态 ────────────────────────────────────────────────
    if synced_ids and not args.dry_run:
        # latest_note 是时间最新的那条（fetch 已按 created_at 升序排列，取最后一条）
        latest_id = (latest_note.id if latest_note else synced_ids[-1])
        state.update(latest_id, synced_ids)

    # ── 7. 打印摘要 ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if args.dry_run:
        print("📋 [dry-run] 同步预览完成（未写入任何文件）")
    else:
        print("📋 同步完成")

    print(f"   本次同步：{len(synced_ids)} 条")
    if type_counter:
        type_names = {
            "podcast": "播客", "voice": "语音备忘", "article": "文章",
            "book": "读书笔记", "work": "工作笔记", "unknown": "其他",
        }
        type_detail = " | ".join(
            f"{type_names.get(t, t)}×{n}" for t, n in sorted(type_counter.items())
        )
        print(f"   类型分布：{type_detail}")
    if latest_note:
        print(f"   最新笔记：{latest_note.created_date} ｜ {latest_note.title[:50]}")
    if errors:
        print(f"   ⚠️  失败 {len(errors)} 条：{[e[0] for e in errors]}")
    if not args.dry_run:
        print(f"   输出目录：{config.obsidian_vault}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

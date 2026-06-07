#!/usr/bin/env python3
"""
backfill_voice_memos.py — 语音备忘内容补全

针对 Get笔记沉淀/07_语音日记/ 下的旧格式语音备忘文件，
重新从 Get API 拉取 AI整理内容 + 原始转写，并原地覆写文件。

跳过条件（任一满足即跳过）：
  1. 文件已同时含 "## 📝 笔记内容" 和 "## 🎙 录音原文"（已是最新格式）
  2. 文件 frontmatter 中无 id 字段

用法：
  python3 /tmp/backfill_voice_memos.py             # dry-run（只打印，不写入）
  python3 /tmp/backfill_voice_memos.py --execute   # 实际写入
"""
import sys
import re
from pathlib import Path

# ── 加载 Get-Notes 同步工具 ─────────────────────────────────────────────────
GET_NOTES_ROOT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Going Growing/Going Growing-os/Get-Notes"
sys.path.insert(0, str(GET_NOTES_ROOT))

from get_notes.auth import GetNotesAuth
from get_notes.client import GetNotesClient
from get_notes.fetcher import GetNotesFetcher
from get_notes.parser import parse_note
from get_notes.renderer import ObsidianRenderer
from get_notes.config import config

VAULT_VOICE_DIR = config.obsidian_vault / "07_语音日记"

# 用于判断文件当前状态
RE_ID = re.compile(r'^id:\s*get-(\d+)', re.MULTILINE)

def get_note_id(text: str):
    """从 frontmatter 提取 note id（去掉 'get-' 前缀）"""
    m = RE_ID.search(text)
    return m.group(1) if m else None

def classify_file(text: str) -> str:
    """
    返回：
      'ok'       — 已有双节（📝 笔记内容 + 🎙 录音原文）
      'ai_only'  — 只有旧格式 AI 内容（## 🎙 内容）
      'trans_only' — 只有旧格式转写（## 🎙 转写内容）
      'mixed'    — 其他有日期id的文件
    """
    has_new_ai    = "## 📝 笔记内容" in text
    has_new_trans = "## 🎙 录音原文" in text
    if has_new_ai and has_new_trans:
        return 'ok'
    has_old_ai    = "## 🎙 内容" in text
    has_old_trans = "## 🎙 转写内容" in text
    if has_old_ai:
        return 'ai_only'
    if has_old_trans:
        return 'trans_only'
    return 'mixed'

def scan_targets() -> list[tuple[Path, str, str]]:
    """
    扫描 07_语音日记/ 下所有 .md 文件，返回需要补全的列表。
    每个元素：(file_path, note_id, classify_result)
    """
    targets = []
    skipped_ok = 0
    skipped_no_id = 0

    for path in sorted(VAULT_VOICE_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        cat = classify_file(text)
        if cat == 'ok':
            skipped_ok += 1
            continue
        note_id = get_note_id(text)
        if not note_id:
            skipped_no_id += 1
            continue
        targets.append((path, note_id, cat))

    print(f"  已是新格式（跳过）  : {skipped_ok} 个")
    print(f"  无 id 字段（跳过）  : {skipped_no_id} 个")
    return targets

def run(dry_run: bool = True):
    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"\n{'='*60}")
    print(f"  语音备忘内容补全 [{mode}]")
    print(f"{'='*60}\n")

    # 扫描目标文件
    print("扫描 07_语音日记/ ...")
    targets = scan_targets()
    ai_only   = [(p, nid, c) for p, nid, c in targets if c == 'ai_only']
    trans_only = [(p, nid, c) for p, nid, c in targets if c == 'trans_only']
    others    = [(p, nid, c) for p, nid, c in targets if c == 'mixed']
    print(f"  需补全（旧 AI 整理格式）: {len(ai_only)} 个")
    print(f"  需补全（旧转写格式）    : {len(trans_only)} 个")
    print(f"  其他需处理             : {len(others)} 个")
    print(f"  合计                   : {len(targets)} 个\n")

    if not targets:
        print("✅ 无需补全，所有语音备忘已是最新格式。")
        return

    # 初始化 API 客户端
    print("正在初始化 Get API 客户端...")
    auth    = GetNotesAuth()
    token   = auth.get_token()
    client  = GetNotesClient(token)
    fetcher = GetNotesFetcher(client)
    renderer = ObsidianRenderer()
    print("  ✅ 客户端初始化成功\n")

    # 补全处理
    success = 0
    skipped_api_empty = 0
    errors = []

    print(f"{'─'*60}")
    print(f"开始逐条重拉（共 {len(targets)} 条）")
    print(f"{'─'*60}")

    for i, (path, note_id, cat) in enumerate(targets, 1):
        rel = path.relative_to(config.obsidian_vault)
        cat_label = {"ai_only": "仅AI整理", "trans_only": "仅转写", "mixed": "其他"}.get(cat, cat)
        try:
            # 构造最小 raw note dict
            raw = {"note_id": note_id, "id": note_id}

            # 重拉详情 + transcript
            full_raw = fetcher.fetch_note_with_detail(raw)
            note = parse_note(full_raw)

            # 检查拉取结果
            has_body = bool(note.body_text)
            has_trans = bool(note.transcript)
            gain = []
            if has_body:   gain.append("AI整理")
            if has_trans:  gain.append("转写")
            gain_str = "+".join(gain) if gain else "（均为空）"

            if not has_body and not has_trans:
                print(f"  ⚠️  [{i}/{len(targets)}] {rel.name}  API 两者均空，跳过覆写")
                skipped_api_empty += 1
                continue

            # 生成新内容
            content = renderer.render(note)

            print(f"  {'[dry]' if dry_run else '✅'} [{i}/{len(targets)}] {rel.name}")
            print(f"        {cat_label} → {gain_str}")

            if not dry_run:
                path.write_text(content, encoding="utf-8")
            success += 1

        except Exception as e:
            print(f"  ❌ [{i}/{len(targets)}] {rel.name}  失败：{e}")
            errors.append((str(rel), str(e)))

    # 汇总
    print(f"\n{'='*60}")
    print(f"汇总：")
    print(f"  {'预计补全' if dry_run else '已补全'}  : {success} 个")
    print(f"  API 内容为空  : {skipped_api_empty} 个（保留原文件不动）")
    print(f"  失败          : {len(errors)} 个")
    if errors:
        for name, err in errors:
            print(f"    ✗ {name}: {err}")
    if dry_run:
        print(f"\n  以上为预览。执行请传参 --execute")
    else:
        print(f"\n  ✅ 完成！")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    dry = "--execute" not in sys.argv
    run(dry_run=dry)

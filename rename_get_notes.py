#!/usr/bin/env python3
"""
统一 Get笔记沉淀 文件命名规范
目标格式：YYYY-MM-DD_标题.md（日期前缀）
"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Going Knowledge/Get笔记沉淀"

DATE_PAT = r'\d{4}-\d{2}-\d{2}'

# 格式判断
RE_NEW        = re.compile(r'^(' + DATE_PAT + r')_(.+)\.md$')            # 日期_标题.md  ✅
RE_TRANSITION = re.compile(r'^(' + DATE_PAT + r')_(.+)_(' + DATE_PAT + r')\.md$')  # 日期_标题_日期.md
RE_OLD        = re.compile(r'^(.+)_(' + DATE_PAT + r')\.md$')            # 标题_日期.md

def classify(filename):
    if RE_TRANSITION.match(filename):
        return 'transition'
    if RE_NEW.match(filename):
        return 'new'
    if RE_OLD.match(filename):
        return 'old'
    return 'none'

def scan():
    """扫描所有 .md 文件，返回分类列表"""
    results = {'new': [], 'transition': [], 'old': [], 'none': []}
    for path in sorted(BASE_DIR.rglob("*.md")):
        cat = classify(path.name)
        results[cat].append(path)
    return results

def build_new_name_map(files):
    """
    对每个文件计算目标文件名。
    old: 标题_日期.md  → 日期_标题.md
    transition: 日期_标题_日期.md → 日期_标题.md
    返回: {path: new_path}
    """
    mapping = {}
    for path in files:
        name = path.name
        cat = classify(name)
        if cat == 'old':
            m = RE_OLD.match(name)
            title, date = m.group(1), m.group(2)
            new_name = f"{date}_{title}.md"
        elif cat == 'transition':
            m = RE_TRANSITION.match(name)
            date, title = m.group(1), m.group(2)
            new_name = f"{date}_{title}.md"
        else:
            continue
        new_path = path.parent / new_name
        mapping[path] = new_path
    return mapping

def find_duplicates(old_files, new_files, transition_files):
    """
    找出旧格式文件中，已有新格式或过渡格式对应文件的（可删除）。
    key = (directory, normalized_title_without_all_dates)
    """
    # 已存在文件的 key 集合（新格式 + 过渡格式 → 处理后的新格式）
    existing_keys = set()

    # 新格式文件的 key
    for path in new_files:
        m = RE_NEW.match(path.name)
        if m:
            date, title = m.group(1), m.group(2)
            existing_keys.add((str(path.parent), title.lower()))

    # 过渡格式文件的 key（处理后去掉尾部日期）
    for path in transition_files:
        m = RE_TRANSITION.match(path.name)
        if m:
            date, title = m.group(1), m.group(2)
            existing_keys.add((str(path.parent), title.lower()))

    to_delete = []
    to_rename = []

    for path in old_files:
        m = RE_OLD.match(path.name)
        if not m:
            continue
        title, date = m.group(1), m.group(2)
        key = (str(path.parent), title.lower())
        if key in existing_keys:
            to_delete.append(path)
        else:
            to_rename.append(path)

    return to_delete, to_rename

def run(dry_run=True):
    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"\n{'='*60}")
    print(f"  Get笔记沉淀 命名规范统一 [{mode}]")
    print(f"{'='*60}\n")

    files = scan()
    print(f"扫描结果：")
    print(f"  新格式 (日期_标题)      : {len(files['new'])} 个")
    print(f"  旧格式 (标题_日期)      : {len(files['old'])} 个")
    print(f"  过渡格式 (日期_标题_日期): {len(files['transition'])} 个")
    print(f"  无日期文件              : {len(files['none'])} 个")
    print()

    # ── 阶段1：找出可删除的旧格式文件 ──
    to_delete, to_rename_old = find_duplicates(files['old'], files['new'], files['transition'])

    print(f"{'─'*60}")
    print(f"阶段1：删除旧格式重复文件（{len(to_delete)} 个）")
    print(f"{'─'*60}")
    for path in to_delete:
        rel = path.relative_to(BASE_DIR)
        print(f"  🗑  {rel}")
        if not dry_run:
            path.unlink()
    if not to_delete:
        print("  （无）")
    print()

    # ── 阶段2：重命名剩余旧格式文件 ──
    mapping_old = build_new_name_map(to_rename_old)
    print(f"{'─'*60}")
    print(f"阶段2：重命名旧格式文件（{len(mapping_old)} 个）")
    print(f"{'─'*60}")
    skipped = []
    for src, dst in sorted(mapping_old.items(), key=lambda x: str(x[0])):
        rel_src = src.relative_to(BASE_DIR)
        rel_dst = dst.relative_to(BASE_DIR)
        if dst.exists():
            skipped.append((rel_src, rel_dst, "目标已存在"))
            print(f"  ⚠️  跳过: {rel_src.name}  →  {rel_dst.name}  (目标已存在)")
        else:
            print(f"  ✏️  {rel_src.name}  →  {rel_dst.name}")
            if not dry_run:
                src.rename(dst)
    if not mapping_old:
        print("  （无）")
    print()

    # ── 阶段3：重命名过渡格式文件 ──
    mapping_trans = build_new_name_map(files['transition'])
    print(f"{'─'*60}")
    print(f"阶段3：重命名过渡格式文件（{len(mapping_trans)} 个）")
    print(f"{'─'*60}")
    for src, dst in sorted(mapping_trans.items(), key=lambda x: str(x[0])):
        rel_src = src.relative_to(BASE_DIR)
        rel_dst = dst.relative_to(BASE_DIR)
        if dst.exists():
            print(f"  ⚠️  跳过: {rel_src.name}  →  {rel_dst.name}  (目标已存在)")
        else:
            print(f"  ✏️  {rel_src.name}  →  {rel_dst.name}")
            if not dry_run:
                src.rename(dst)
    if not mapping_trans:
        print("  （无）")
    print()

    # ── 汇总 ──
    print(f"{'='*60}")
    print(f"汇总：")
    print(f"  删除   : {len(to_delete)} 个")
    print(f"  重命名 : {len(mapping_old) + len(mapping_trans)} 个")
    print(f"  跳过   : {len(skipped)} 个（目标已存在，需手动检查）")
    if dry_run:
        print(f"\n  以上为预览。执行请传参 --execute")
    else:
        print(f"\n  ✅ 完成！")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    dry = "--execute" not in sys.argv
    run(dry_run=dry)

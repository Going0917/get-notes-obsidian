# Get 笔记 → Obsidian 同步工具

> 将 [Get 笔记](https://www.biji.com/)（罗辑思维旗下 AI 笔记应用）的内容自动同步到 Obsidian Vault，按笔记类型分类保存为标准 Markdown 文件。

---

## 功能特性

- **增量同步**：只拉取上次同步后新增的笔记，避免重复处理
- **全量同步**：一键重新同步所有历史笔记（`--full-sync`）
- **自动类型识别**：
  - 🎙 `播客笔记` — 小宇宙、喜马拉雅、Spotify 等平台
  - 🎤 `语音备忘` — 个人录音笔记
  - 📰 `文章剪藏` — 网页、小红书等链接收藏
  - 📚 `读书笔记` — 书摘、阅读笔记
  - 💼 `工作笔记` — 含工作相关标签的内容
  - 📄 `其他笔记` — 无法识别类型时的兜底分类
- **结构化输出**：每篇笔记包含 YAML frontmatter、AI 总结、章节、金句、转写原文
- **智能 Token 管理**：首次登录后自动刷新，约 90 天内无需重新登录
- **防重复保护**：写入前检查目标文件是否已存在

---

## 输出目录结构

```
Obsidian Vault/
└── Get笔记沉淀/
    ├── 播客笔记/
    │   └── 2026-03/
    │       └── 小宇宙_AI时代的认知革命_2026-03-15.md
    ├── 语音备忘/
    │   └── 2026-03/
    │       └── 语音备忘_143521_2026-03-15.md
    ├── 文章剪藏/
    │   └── 2026-03/
    │       └── 标题_2026-03-15.md
    ├── 读书笔记/
    │   └── 2026-03/
    │       └── 书名_读书笔记_2026-03-15.md
    ├── 工作笔记/
    └── 其他笔记/
```

---

## 环境要求

- Python 3.9+
- [Get 笔记](https://www.biji.com/) 账号（已有笔记内容）
- [Obsidian](https://obsidian.md/) 已安装并创建 Vault

---

## 安装

```bash
# 1. 克隆项目
git clone https://github.com/YOUR_USERNAME/get-notes-obsidian.git
cd get-notes-obsidian

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装 Playwright 浏览器（首次登录需要）
playwright install chromium

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，填写你的 Obsidian Vault 路径
```

---

## 配置

编辑 `.env` 文件：

```ini
# 必填：Obsidian Vault 中用于存放 Get 笔记的目录
OBSIDIAN_VAULT_PATH=/Users/your-name/Documents/Obsidian Vault/Get笔记沉淀

# 可选：每次 API 分页大小（默认 50）
# SYNC_LIMIT=50
```

> ⚠️ `.env` 文件已被 `.gitignore` 排除，不会提交到 Git。

---

## 使用方法

### 增量同步（推荐日常使用）

```bash
python3 sync.py
```

### 其他模式

```bash
# 预览有哪些新笔记（不写文件）
python3 sync.py --dry-run

# 全量重新同步所有笔记
python3 sync.py --full-sync

# 只同步指定类型
python3 sync.py --type podcast    # 只同步播客
python3 sync.py --type voice      # 只同步语音备忘
python3 sync.py --type article    # 只同步文章剪藏
python3 sync.py --type book       # 只同步读书笔记
python3 sync.py --type work       # 只同步工作笔记

# 限制本次同步数量
python3 sync.py --limit 10
```

### 首次运行

首次运行时，程序会自动打开浏览器，引导你完成 Get 笔记登录：

1. 浏览器打开后，点击登录（支持手机扫码或账号密码）
2. 登录成功、看到笔记列表后，回到终端按 **Enter** 继续
3. Token 会自动保存到 `.tokens/tokens.json`，后续运行无需重复登录

---

## 同步输出示例

```
============================================================
📥 Get 笔记同步工具
============================================================
📂 输出目录：/Users/your-name/Documents/Obsidian Vault/Get笔记沉淀
📊 历史累计同步 0 条，上次同步时间：从未同步
🔍 开始增量拉取（上次位置：无，首次全量）
📋 找到 12 条新笔记，开始拉取详情...

🚀 开始同步 12 条笔记...

  ✅ [1/12] podcast  | 2026-03-10 | AI 时代的认知革命
  ✅ [2/12] voice    | 2026-03-11 | 语音备忘_143521_2026-03-11.md
  ✅ [3/12] article  | 2026-03-12 | 如何构建第二大脑
  ...

============================================================
📋 同步完成
   本次同步：12 条
   类型分布：播客×5 | 文章×4 | 语音备忘×2 | 读书笔记×1
   最新笔记：2026-03-15 ｜ AI 时代的认知革命
   输出目录：/Users/your-name/Documents/Obsidian Vault/Get笔记沉淀
============================================================
```

---

## 笔记文件格式

每篇笔记包含完整的 YAML frontmatter 和结构化内容：

```markdown
---
id: get-1904618693187502944
type: podcast
source: "小宇宙"
episode: "AI 时代的认知革命"
url: https://www.xiaoyuzhoufm.com/episode/...
date: 2026-03-15
tags: [podcast, ai, 认知]
synced_at: 2026-03-18T12:00:00+00:00
---

# AI 时代的认知革命

> 来源：[小宇宙](https://...)｜时长：52min｜2026-03-15

---

**目录：** [📝 AI 总结](#-ai-总结) · [🏷 重点章节](#-重点章节) · [💬 金句摘录](#-金句摘录)

## 📝 AI 总结

...

## 🏷 重点章节

### 00:15:44 — 什么是认知革命
...

## 💬 金句摘录

> "在 AI 时代，脑子里的想法才是核心。"
```

---

## 自定义分类

### 添加工作笔记关键词

在 `get_notes/parser.py` 中修改 `_WORK_TAGS`：

```python
_WORK_TAGS = {"工作", "work", "职场", "项目", "okr",
              # 添加你自己的公司/行业词汇：
              "腾讯", "字节", "设计", "产品", ...}
```

### 添加播客平台

在 `get_notes/parser.py` 中修改 `_PODCAST_URL_DOMAINS`（URL 匹配，精确）或 `_PODCAST_PLATFORMS`（名称匹配，宽松）。

### 屏蔽不想同步的笔记

在 `get_notes/parser.py` 中修改 `BLOCKED_NOTE_IDS`：

```python
BLOCKED_NOTE_IDS: set[str] = {
    "1894909191618305632",   # 不想要的笔记 ID
}
```

> 提示：运行 `python3 sync.py --dry-run` 可以看到所有笔记的 ID 信息。

---

## 项目结构

```
get-notes-obsidian/
├── .env.example          # 配置示例
├── .gitignore
├── requirements.txt
├── sync.py               # 主入口
└── get_notes/
    ├── auth.py           # Token 获取/刷新（Playwright 登录）
    ├── client.py         # API 请求封装
    ├── config.py         # 配置管理
    ├── fetcher.py        # 分页拉取 + 增量控制
    ├── parser.py         # 笔记类型识别 + 内容结构化
    ├── renderer.py       # Obsidian Markdown 渲染
    └── state.py          # 增量同步状态管理
```

---

## 常见问题

**Q: 首次运行时浏览器打开后我应该做什么？**

登录 Get 笔记（biji.com）即可，看到笔记列表后回到终端按 Enter。程序会自动提取登录凭证并保存。

**Q: Token 多久过期？**

JWT token 有效期约 1 小时，程序会自动刷新。Refresh Token 有效期约 90 天，无需手动操作。90 天后再次运行时会重新打开浏览器登录。

**Q: 如何重置并全量重新同步？**

```bash
rm -f .sync_state.json
python3 sync.py --full-sync
```

**Q: 已同步的笔记内容有更新，能重新同步吗？**

目前笔记文件一旦创建不会被覆盖（防重复设计）。如需重新同步某篇，手动删除对应的 `.md` 文件后重新运行即可。

**Q: 支持 Windows 吗？**

理论上支持（Python + Playwright 均跨平台），但目前仅在 macOS 上测试过。欢迎提 Issue 反馈。

---

## 致谢

- [Get 笔记 / biji.com](https://www.biji.com/) — 数据来源
- [Obsidian](https://obsidian.md/) — 知识管理工具
- [Playwright](https://playwright.dev/) — 浏览器自动化登录

---

## License

MIT

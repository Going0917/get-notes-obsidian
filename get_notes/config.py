"""
config.py — 配置管理
从 .env 加载配置，定义全局 Config 对象
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env（相对于本模块所在的项目根目录）
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")


@dataclass
class Config:
    # ── API 地址 ─────────────────────────────────────────────────
    base_url: str = "https://get-notes.luojilab.com"
    auth_url: str = "https://notes-api.biji.com"

    # ── Token 本地缓存路径 ────────────────────────────────────────
    token_store: Path = field(default_factory=lambda: _ROOT / ".tokens" / "tokens.json")

    # ── 增量同步状态文件 ──────────────────────────────────────────
    state_file: Path = field(default_factory=lambda: _ROOT / ".sync_state.json")

    # ── Obsidian 输出路径（从 .env 读取） ─────────────────────────
    obsidian_vault: Path = field(default_factory=lambda: Path(
        os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
    ))

    # ── 同步行为 ──────────────────────────────────────────────────
    sync_limit: int = field(default_factory=lambda: int(os.getenv("SYNC_LIMIT", "50")))

    def validate(self):
        """启动时校验关键配置"""
        if not self.obsidian_vault or str(self.obsidian_vault) == ".":
            raise ValueError(
                "❌ 未设置 OBSIDIAN_VAULT_PATH\n"
                "请在 .env 文件中添加：\n"
                "OBSIDIAN_VAULT_PATH=/你的/Obsidian Vault/Get笔记沉淀"
            )
        return self


# 全局单例
config = Config().validate()

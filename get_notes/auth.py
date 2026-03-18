"""
auth.py — Token 获取 / 刷新 / 持久化

三层降级策略：
1. 本地缓存 JWT 未过期 → 直接使用
2. JWT 过期 + refresh_token 有效 → 静默刷新
3. 两者均过期 → Playwright 打开浏览器引导登录
"""
from __future__ import annotations
import json
import time
import requests
from pathlib import Path
from datetime import datetime

from .config import config


class GetNotesAuth:
    def __init__(self):
        self.token_store: Path = config.token_store
        self.auth_url: str = config.auth_url
        # 提前 5 分钟刷新，避免 token 在请求途中过期
        self._refresh_margin_sec = 300

    # ────────────────────────────────────────────────
    # 公开接口
    # ────────────────────────────────────────────────

    def get_token(self) -> str:
        """返回有效的 Bearer Token（自动处理刷新和重新登录）"""
        tokens = self._load_tokens()

        if tokens is None:
            print("🔐 未找到本地 Token，即将打开浏览器进行首次登录...")
            tokens = self._browser_login()
        elif self._is_token_valid(tokens):
            return tokens["token"]
        elif self._is_refresh_token_valid(tokens):
            print("🔄 Token 已过期，正在静默刷新...")
            tokens = self._refresh_token(tokens)
        else:
            print("⚠️  Token 和 refresh_token 均已过期，即将重新登录...")
            tokens = self._browser_login()

        return tokens["token"]

    # ────────────────────────────────────────────────
    # 私有方法
    # ────────────────────────────────────────────────

    def _load_tokens(self) -> dict | None:
        """从 .tokens/tokens.json 读取，文件不存在则返回 None"""
        if not self.token_store.exists():
            return None
        try:
            with open(self.token_store, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            return None

    def _save_tokens(self, tokens: dict):
        """写入 .tokens/tokens.json，目录不存在则自动创建"""
        self.token_store.parent.mkdir(parents=True, exist_ok=True)
        tokens["saved_at"] = datetime.now().isoformat(timespec="seconds")
        with open(self.token_store, "w", encoding="utf-8") as f:
            json.dump(tokens, f, ensure_ascii=False, indent=2)

    def _is_token_valid(self, tokens: dict) -> bool:
        """JWT token 是否仍在有效期内（含 5 分钟余量）"""
        expire_at = tokens.get("token_expire_at", 0)
        return time.time() < (expire_at - self._refresh_margin_sec)

    def _is_refresh_token_valid(self, tokens: dict) -> bool:
        """refresh_token 是否仍在有效期内"""
        expire_at = tokens.get("refresh_token_expire_at", 0)
        return time.time() < expire_at

    def _refresh_token(self, tokens: dict) -> dict:
        """
        调用 refresh API 获取新 JWT token
        POST https://notes-api.biji.com/account/v2/web/user/auth/refresh

        真实响应结构：
        { "c": { "success": true, "token": {
            "token": "...", "token_expire_at": ...,
            "refresh_token": "...", "refresh_token_expire_at": ...
        }}}
        """
        url = f"{self.auth_url}/account/v2/web/user/auth/refresh"
        resp = requests.post(
            url,
            json={"refresh_token": tokens["refresh_token"]},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # 实际 token 在 c.token 子对象里
        c = data.get("c", {})
        token_obj = c.get("token", {})

        # 构建规范化的 tokens dict
        new_tokens = {
            "token":                    token_obj.get("token") or c.get("token"),
            "token_expire_at":          token_obj.get("token_expire_at") or c.get("token_expire_at", 0),
            "refresh_token":            token_obj.get("refresh_token") or tokens["refresh_token"],
            "refresh_token_expire_at":  token_obj.get("refresh_token_expire_at") or tokens.get("refresh_token_expire_at", 0),
        }

        if not new_tokens["token"]:
            raise RuntimeError(f"❌ Token 刷新失败，响应中未找到 token 字段。响应：{data}")

        self._save_tokens(new_tokens)
        print("✅ Token 已自动刷新")
        return new_tokens

    def _browser_login(self) -> dict:
        """
        用 Playwright 打开浏览器，引导用户登录，
        登录成功后从 localStorage 提取 token 并保存。
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "❌ 未安装 Playwright，请运行：\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        login_url = "https://www.biji.com"

        print("\n" + "=" * 60)
        print("🌐 即将打开浏览器，请在浏览器中完成 Get 笔记登录。")
        print("   ① 浏览器打开后，点击登录，用手机扫码或账号密码登录")
        print("   ② 登录成功、看到笔记列表后，回到此窗口按 Enter 继续")
        print("=" * 60 + "\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=200)
            context = browser.new_context()
            page = context.new_page()
            page.goto(login_url)

            input("✋ 请在浏览器中完成登录，然后按 Enter 继续...")

            # 从 localStorage 提取 token 信息（biji.com 使用 localStorage）
            tokens = page.evaluate("""() => {
                // 尝试多种可能的 key 名称
                const keyMap = [
                    ['token', 'token_expire_at', 'refresh_token', 'refresh_token_expire_at'],
                    ['access_token', 'access_token_expire_at', 'refresh_token', 'refresh_token_expire_at'],
                    ['userToken', 'tokenExpireAt', 'refreshToken', 'refreshTokenExpireAt'],
                ];
                for (const [tk, te, rt, re] of keyMap) {
                    const t = localStorage.getItem(tk);
                    if (t) {
                        return {
                            token: t,
                            token_expire_at: parseInt(localStorage.getItem(te) || '0'),
                            refresh_token: localStorage.getItem(rt) || '',
                            refresh_token_expire_at: parseInt(localStorage.getItem(re) || '0'),
                            _raw_keys: Object.keys(localStorage),
                        };
                    }
                }
                // 找不到就把所有 localStorage 内容返回，便于调试
                const all = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    all[k] = localStorage.getItem(k);
                }
                return { token: null, _debug_all: all };
            }""")

            # 如果 localStorage 没有，尝试从 cookies 提取
            if not tokens.get("token"):
                cookies = context.cookies()
                token_cookie = next((c for c in cookies if 'token' in c['name'].lower()), None)
                if token_cookie:
                    tokens["token"] = token_cookie["value"]
                    tokens["token_expire_at"] = int(token_cookie.get("expires", 0))

            browser.close()

        # 调试信息
        if not tokens.get("token"):
            debug_info = tokens.get("_debug_all") or tokens.get("_raw_keys") or {}
            raise RuntimeError(
                "❌ 未能获取到 Token，请确认已在浏览器中完成登录。\n"
                f"   localStorage 中的所有 key：{list(debug_info.keys()) if isinstance(debug_info, dict) else debug_info}\n"
                "   请将以上信息反馈给维护者，以便更新 auth.py 的字段名。"
            )

        self._save_tokens(tokens)
        expire_days = max(0, int((tokens.get("refresh_token_expire_at", 0) - time.time()) / 86400))
        print(f"✅ Token 已获取并保存（refresh_token 有效期约 {expire_days} 天）")
        return tokens

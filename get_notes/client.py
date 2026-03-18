"""
client.py — Get 笔记 API 请求封装

封装三个核心端点：
- get_notes_list()     笔记列表（支持分页）
- get_note_detail()    笔记详情
- get_note_original()  原始转写（含时间戳）
"""
import time
import requests
from typing import Optional

from .config import config


class GetNotesClient:
    def __init__(self, token: str):
        self.base_url = config.base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        # 请求间隔，避免频率过高（社区实践建议 500ms）
        self._request_interval = 0.5

    # ────────────────────────────────────────────────
    # 公开接口
    # ────────────────────────────────────────────────

    def get_notes_list(
        self,
        limit: int = 50,
        since_id: Optional[str] = None,
    ) -> dict:
        """
        获取笔记列表（分页）
        GET /voicenotes/web/notes

        参数：
            limit:    每页条数（最大 50）
            since_id: 游标分页，填写上一页最后一条的 note_id

        返回：
            {
                "list": [...],
                "total_items": 100,
                "has_more": True
            }
        """
        params: dict = {"limit": limit}
        if since_id:
            params["since_id"] = since_id

        resp = self._get("/voicenotes/web/notes", params=params)
        return resp.get("c", resp)

    def get_note_detail(self, note_id: str) -> dict:
        """
        获取笔记详情
        GET /voicenotes/web/notes/{note_id}

        返回原始 API 响应中的 "c" 字段（笔记详情对象）
        """
        resp = self._get(f"/voicenotes/web/notes/{note_id}")
        return resp.get("c", resp)

    def get_note_original(self, note_id: str) -> dict:
        """
        获取原始转写内容（带时间戳）
        GET /voicenotes/web/notes/{note_id}/original

        返回原始 API 响应中的 "c" 字段（转写内容对象）
        """
        resp = self._get(f"/voicenotes/web/notes/{note_id}/original")
        return resp.get("c", resp)

    # ────────────────────────────────────────────────
    # 私有方法
    # ────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """发送 GET 请求，统一错误处理"""
        url = f"{self.base_url}{path}"
        time.sleep(self._request_interval)

        try:
            resp = self.session.get(url, params=params, timeout=30)
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"❌ 网络连接失败：{e}") from e
        except requests.exceptions.Timeout:
            raise RuntimeError(f"❌ 请求超时（URL: {url}）")

        if resp.status_code == 401:
            raise RuntimeError(
                "❌ Token 已失效（HTTP 401）\n"
                "请删除 .tokens/tokens.json 后重新运行，将触发浏览器重新登录。"
            )
        if resp.status_code == 429:
            raise RuntimeError("❌ 请求频率过高（HTTP 429），请稍后重试。")
        if not resp.ok:
            raise RuntimeError(
                f"❌ API 请求失败：HTTP {resp.status_code}\n"
                f"URL: {url}\n"
                f"响应：{resp.text[:500]}"
            )

        try:
            return resp.json()
        except ValueError as e:
            raise RuntimeError(f"❌ API 返回了非 JSON 响应：{resp.text[:200]}") from e

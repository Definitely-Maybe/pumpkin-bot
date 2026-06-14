"""微信协议层 — XML 解析 / token 管理 / 签名验证 / 客服消息 API。"""

import hashlib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Optional

import aiohttp

from .config import WECHAT_APPID, WECHAT_SECRET

logger = logging.getLogger(__name__)

UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


class WeChatProtocol:
    """微信协议处理——无外部依赖，手写 XML 解析。"""

    _access_token: Optional[str] = None
    _token_expires_at: float = 0.0
    _last_error: Optional[dict] = None

    # ─── 签名验证 ─────────────────────────────────

    @staticmethod
    def verify_signature(token: str, signature: str,
                         timestamp: str, nonce: str) -> bool:
        """验证微信签名。"""
        if not signature or not timestamp or not nonce:
            return False
        tmp_list = sorted([token, timestamp, nonce])
        tmp_str = "".join(tmp_list)
        calculated = hashlib.sha1(tmp_str.encode()).hexdigest()
        return calculated == signature

    # ─── XML 解析 ─────────────────────────────────

    @staticmethod
    def parse_message(xml_data: str) -> Optional[dict]:
        """解析微信推送的 XML 消息。"""
        try:
            root = ET.fromstring(xml_data)
            msg_type = root.findtext("MsgType", "unknown")
            from_user = root.findtext("FromUserName", "")
            to_user = root.findtext("ToUserName", "")

            if msg_type == "text":
                content = root.findtext("Content", "")
            elif msg_type == "image":
                content = "[图片消息——暂不支持]"
            elif msg_type == "voice":
                content = "[语音消息——暂不支持]"
            elif msg_type == "event":
                event = root.findtext("Event", "")
                content = f"[事件——{event}]"
            else:
                content = f"[不支持的消息类型: {msg_type}]"

            return {
                "from_user": from_user,
                "to_user": to_user,
                "msg_type": msg_type,
                "content": content,
                "msg_id": root.findtext("MsgId", ""),
                "create_time": root.findtext("CreateTime", ""),
            }
        except ET.ParseError:
            logger.warning("XML 解析失败")
            return None

    # ─── access_token ─────────────────────────────

    @classmethod
    async def get_access_token(cls) -> Optional[str]:
        """获取/刷新 access_token。缓存到过期前 5 分钟。"""
        now = time.time()
        if cls._access_token and now < cls._token_expires_at - 300:
            return cls._access_token

        url = (
            "https://api.weixin.qq.com/cgi-bin/token"
            f"?grant_type=client_credential&appid={WECHAT_APPID}&secret={WECHAT_SECRET}"
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
        except Exception:
            logger.exception("获取 access_token 失败")
            return None

        if "access_token" in data:
            cls._access_token = data["access_token"]
            cls._token_expires_at = now + data.get("expires_in", 7200)
            cls._last_error = None
            return cls._access_token

        cls._last_error = data
        logger.warning(f"access_token 获取失败: {data}")
        return None

    # ─── 客服消息推送 ─────────────────────────────

    @staticmethod
    def normalize_outgoing_text(content: str) -> str:
        """Restore literal unicode escapes before sending text to WeChat."""
        if "\\u" not in content:
            return content
        return UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), content)

    @classmethod
    async def send_custom_message(cls, user_openid: str, content: str) -> bool:
        """通过客服消息 API 推送文本。"""
        token = await cls.get_access_token()
        if not token:
            return False

        url = (
            "https://api.weixin.qq.com/cgi-bin/message/custom/send"
            f"?access_token={token}"
        )
        body = {
            "touser": user_openid,
            "msgtype": "text",
            "text": {"content": cls.normalize_outgoing_text(content)},
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
                    if data.get("errcode") == 0:
                        cls._last_error = None
                        logger.info("客服消息发送成功")
                        return True
                    cls._last_error = data
                    logger.warning(f"客服消息失败: {data}")
                    return False
        except Exception:
            logger.exception("客服消息网络错误")
            cls._last_error = {"errmsg": "network error"}
            return False

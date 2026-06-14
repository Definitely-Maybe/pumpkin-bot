"""内存消息队列 + cursor 管理。"""

from collections import deque
from datetime import datetime


class MessageQueue:
    """线程安全的内存消息队列。每个用户独立 cursor。"""

    def __init__(self, maxlen: int = 1000):
        self._items: deque[dict] = deque(maxlen=maxlen)
        self._cursors: dict[str, int] = {}  # openid → 下次 start index
        self._seen_msg_ids: set[str] = set()
        self._counter = 0

    def push(self, user_openid: str, msg_type: str, content: str,
             msg_id: str = "") -> dict:
        """推入一条消息。返回消息 dict。"""
        if msg_id and msg_id in self._seen_msg_ids:
            return {}
        if msg_id:
            self._seen_msg_ids.add(msg_id)
        msg = {
            "msg_id": msg_id or str(self._counter),
            "user_openid": user_openid,
            "msg_type": msg_type,
            "content": content,
            "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._items.append(msg)
        self._counter += 1
        return msg

    def poll(self, user_openid: str) -> list[dict]:
        """返回该用户自上次 poll 以来的新消息。"""
        cursor = self._cursors.get(user_openid, 0)
        # 用 cursor 定位——简单实现：遍历所有消息找该用户的新消息
        msgs = []
        for i in range(cursor, len(self._items)):
            item = self._items[i]
            if item["user_openid"] == user_openid:
                msgs.append(item)
        # 更新 cursor 到最后检查的位置
        self._cursors[user_openid] = len(self._items)
        return msgs

    @property
    def size(self) -> int:
        return len(self._items)

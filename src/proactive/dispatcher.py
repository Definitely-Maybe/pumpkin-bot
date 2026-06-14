"""主动消息发送接口 — ABC + Terminal 实现。"""

from abc import ABC, abstractmethod
from typing import Optional
import aiosqlite


class Dispatcher(ABC):
    """平台无关的主动消息发送接口。"""

    @abstractmethod
    async def send(self, message: str, user_id: str) -> bool:
        """发送一条主动消息。返回是否成功。"""
        ...

    @abstractmethod
    async def flush_pending(self, user_id: str) -> list[str]:
        """发送用户所有 pending 消息。返回已发送的消息文本列表。"""
        ...


class TerminalDispatcher(Dispatcher):
    """终端实现：print 到 stdout + 写入 outgoing messages 表。"""

    def __init__(self, db: Optional[aiosqlite.Connection] = None):
        self.db = db

    async def send(self, message: str, user_id: str) -> bool:
        """终端模式：直接打印到 stdout。"""
        try:
            print(f"\n[南瓜主动] {message}\n")
            # 写入 outgoing messages 表
            if self.db:
                from ..storage import queries as q
                from ..storage.models import Message, Direction
                await q.insert_message(self.db, Message(
                    user_id=user_id,
                    direction=Direction.OUTGOING,
                    content=message,
                ))
            return True
        except Exception:
            return False

    async def flush_pending(self, user_id: str) -> list[str]:
        """发送用户所有 pending 消息。"""
        if not self.db:
            return []
        from ..storage import queries as q
        pending = await q.get_pending_proactive(self.db, user_id)
        sent = []
        for task in pending:
            msg = task.get("proposed_message", "")
            if not msg:
                continue
            ok = await self.send(msg, user_id)
            if ok:
                await q.mark_proactive_sent(self.db, task["task_id"])
                sent.append(msg)
        return sent

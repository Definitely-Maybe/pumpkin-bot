"""消息收发适配器抽象基类。"""

from abc import ABC, abstractmethod
from typing import Callable, Awaitable


class MessageAdapter(ABC):
    """所有平台适配器必须实现的接口。"""

    platform: str = "unknown"

    @abstractmethod
    async def start(self, on_message: Callable[[str, str], Awaitable[None]]):
        """启动适配器，开始监听消息。

        on_message: 回调函数 (user_id, text) -> None
        """
        ...

    @abstractmethod
    async def send(self, user_id: str, messages: list[str]):
        """发送回复消息。messages 是短句列表，逐条发送。"""
        ...

    @abstractmethod
    async def stop(self):
        """停止适配器。"""
        ...

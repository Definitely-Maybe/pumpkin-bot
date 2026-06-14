"""Adapter ABC — 平台无关的消息收发接口。"""

from abc import ABC, abstractmethod
from typing import Callable, Awaitable


class Adapter(ABC):
    """平台适配器抽象基类。"""

    platform: str

    @abstractmethod
    async def start(self, on_message: Callable[[str, str], Awaitable[None]]):
        """启动平台监听。收到消息时回调 on_message(user_id, text)。"""
        ...

    @abstractmethod
    async def send(self, user_id: str, messages: list[str]):
        """向该平台用户发送回复。"""
        ...

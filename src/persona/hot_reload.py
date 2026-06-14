"""Hot-reload：监听 persona.md / self.md 变化，自动重载。"""

import asyncio
from pathlib import Path
from typing import Callable, Awaitable

from watchfiles import awatch


class HotReload:
    """监听文件变化，触发回调。"""

    def __init__(self):
        self._watchers: list[asyncio.Task] = []

    async def watch(
        self,
        paths: list[str | Path],
        on_change: Callable[[set[str]], Awaitable[None]],
    ):
        """异步监听文件变化。

        paths: 要监听的文件路径列表
        on_change: 变化时调用的异步回调，传入变化的文件路径集合
        """
        resolved = [str(Path(p).resolve()) for p in paths]
        watch_dirs = set(Path(p).parent for p in resolved)

        async def _watcher():
            async for changes in awatch(*watch_dirs):
                changed_files = {str(Path(p[1])) for p in changes}
                relevant = changed_files & set(resolved)
                if relevant:
                    await on_change(relevant)

        task = asyncio.create_task(_watcher())
        self._watchers.append(task)

    async def stop(self):
        for task in self._watchers:
            task.cancel()
        self._watchers.clear()

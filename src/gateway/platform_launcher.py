"""PlatformLauncher — 多平台启动编排。"""

import asyncio
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from .adapter import Adapter
from .mcp_client import MCPHttpClient
from .wechat_adapter import WeChatAdapter

logger = logging.getLogger(__name__)


class PlatformLauncher:
    """编排多平台 Adapter 的启动和停止。"""

    def __init__(self, config: dict, bot_name: str = "南瓜"):
        self.config = config
        self.bot_name = bot_name
        self._adapters: list[Adapter] = []
        self._mcp_process: subprocess.Popen | None = None
        self._mcp_stdout = None
        self._mcp_stderr = None
        self._mcp_client: MCPHttpClient | None = None

    async def launch(self) -> list[Adapter]:
        """启动所有配置的平台。返回 adapter 列表。"""
        platforms_cfg = self.config.get("platforms", {})

        # Terminal
        if platforms_cfg.get("terminal", {}).get("enabled", True):
            from .terminal_adapter import TerminalAdapter
            adapter = TerminalAdapter(bot_name=self.bot_name)
            self._adapters.append(adapter)
            logger.info("Terminal 平台已注册")

        # WeChat
        wechat_cfg = platforms_cfg.get("wechat", {})
        if wechat_cfg.get("enabled", False):
            mcp_port = wechat_cfg.get("mcp_port", 8090)
            mcp_url = f"http://127.0.0.1:{mcp_port}"

            # 启动 MCP server 子进程
            mcp_script = Path(__file__).resolve().parent.parent.parent / "wechat_mcp_server" / "server.py"
            env = {}
            config_key_map = {
                "WECHAT_APPID": "appid",
                "WECHAT_SECRET": "secret",
                "WECHAT_TOKEN": "token",
            }
            for key, config_key in config_key_map.items():
                val = wechat_cfg.get(config_key, "")
                if not val or str(val).startswith(("wx_your_", "your_")):
                    val = os.environ.get(key, "")
                if val:
                    env[key] = str(val)
            env["MCP_PORT"] = str(mcp_port)
            full_env = {**os.environ, **env}
            log_dir = Path(self.config.get("storage", {}).get("log_path", "data/logs"))
            log_dir.mkdir(parents=True, exist_ok=True)
            self._mcp_stdout = open(log_dir / "wechat_mcp.out.log", "a", encoding="utf-8")
            self._mcp_stderr = open(log_dir / "wechat_mcp.err.log", "a", encoding="utf-8")

            logger.info(f"启动 WeChat MCP Server on port {mcp_port}...")
            self._mcp_process = subprocess.Popen(
                [sys.executable, str(mcp_script)],
                env=full_env,
                stdout=self._mcp_stdout,
                stderr=self._mcp_stderr,
            )

            # 等待 MCP server ready
            await self._wait_for_mcp(mcp_url)

            self._mcp_client = MCPHttpClient(mcp_url)
            adapter = WeChatAdapter(self._mcp_client)
            self._adapters.append(adapter)
            logger.info("WeChat 平台已注册")

        return self._adapters

    async def _wait_for_mcp(self, url: str, max_retries: int = 15, interval: float = 1.0):
        """等待 MCP server 健康检查通过。"""
        import aiohttp
        for i in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{url}/health",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            logger.info("MCP Server ready")
                            return
            except Exception:
                pass
            await asyncio.sleep(interval)
        raise RuntimeError("MCP Server 启动超时")

    async def start_all(self, on_message):
        """同时启动所有 adapter。"""
        if not self._adapters:
            raise RuntimeError("没有可用的平台。请在 config.yaml 中启用至少一个平台。")

        tasks = [a.start(on_message) for a in self._adapters]
        await asyncio.gather(*tasks)

    async def shutdown(self):
        """关闭所有 adapter + MCP server。"""
        for adapter in self._adapters:
            if hasattr(adapter, "stop"):
                try:
                    await adapter.stop()
                except Exception:
                    pass

        if self._mcp_client:
            await self._mcp_client.close()

        if self._mcp_process:
            self._mcp_process.terminate()
            try:
                self._mcp_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._mcp_process.kill()
            logger.info("MCP Server 已关闭")

        for stream in (self._mcp_stdout, self._mcp_stderr):
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass

#!/usr/bin/env python
"""南瓜 Bot — 入口脚本。Pipeline 架构。

用法：
    python run.py              # 终端模式
    python run.py --config config.yaml  # 指定配置文件

环境变量：
    DEEPSEEK_API_KEY — DeepSeek API 密钥（必需）
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件（必须在检查环境变量之前）
load_dotenv()

# 将项目根目录加入 Python path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.pipeline import MessageBus
from src.core.session import SessionManager
from src.core.context import ContextAssembler
from src.core.llm import LLMEngine
from src.core.postprocess import PostProcessor
from src.persona.memory import SelfMemory
from src.storage.db import init_db
from src.gateway.platform_launcher import PlatformLauncher
from src.utils.config import load_config
from src.utils.debug import DebugLogger
from src.memory.summary_writer import SummaryWriter
from src.memory.loop_detector import LoopDetector
from src.proactive.dispatcher import TerminalDispatcher


async def _get_active_users(conn) -> list[str]:
    """获取所有互动过的用户 ID。"""
    cursor = await conn.execute("SELECT DISTINCT user_id FROM users")
    rows = await cursor.fetchall()
    return [r["user_id"] for r in rows]


async def main():
    # 检查 API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("错误：未设置 DEEPSEEK_API_KEY 环境变量")
        print("请在 .env 文件中填入你的 API Key（去 https://platform.deepseek.com 获取）")
        sys.exit(1)

    # 解析参数
    config_path = "config.yaml"
    debug_level = 0  # will be overridden by config or CLI

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--config" and i + 1 < len(args):
            config_path = args[i + 1]
            i += 2
        elif args[i].startswith("--debug"):
            if "=" in args[i]:
                debug_level = int(args[i].split("=")[1])
            elif i + 1 < len(args):
                try:
                    debug_level = int(args[i + 1])
                except ValueError:
                    pass  # not a number, skip
                i += 1
            i += 1
        else:
            i += 1

    config = load_config(config_path)

    # CLI --debug overrides config
    if debug_level == 0:
        debug_level = config.get("debug_level", 0)

    # ---- 数据库 ----
    db = await init_db(config["storage"]["db_path"])
    print(f"[bot] 数据库已连接: {config['storage']['db_path']}")

    # ---- 人格加载 ----
    persona_path = config["persona"]["persona_md_path"]
    self_md_path = config["persona"]["self_md_path"]
    self_memory = SelfMemory(self_md_path)
    context_asm = ContextAssembler(persona_path, self_memory, db)
    print(f"[bot] 人格已加载: {persona_path}")

    # ---- LLM 引擎 ----
    llm_cfg = config["llm"]
    llm = LLMEngine(
        model=llm_cfg["model"],
        max_tokens=llm_cfg["max_tokens"],
        temperature=llm_cfg["temperature"],
        base_url=llm_cfg.get("base_url", "https://api.deepseek.com"),
    )
    print(f"[bot] LLM 已初始化: {llm_cfg['model']}")

    # ---- Debug 日志 ----
    debug_logger = DebugLogger(level=debug_level)

    # ---- 记忆组件 ----
    summary_writer = SummaryWriter(llm)
    loop_detector = LoopDetector(llm, db)

    # ---- Pipeline 组件 ----
    session_mgr = SessionManager(db)
    postprocessor = PostProcessor(
        db, llm, summary_writer, loop_detector, branch_detector=None,
        self_memory=self_memory,
        persona_path=persona_path,
        self_md_path=self_md_path,
        config=config,
        debug_logger=debug_logger,
    )

    # ---- Dispatcher 主动消息 ----
    dispatcher = TerminalDispatcher(db)

    # 启动时 flush 所有 pending 消息
    for user_id in await _get_active_users(db):
        await dispatcher.flush_pending(user_id)

    # ---- MessageBus（替换旧的 NanGuaBot）----
    bus = MessageBus(db, session_mgr, context_asm, llm, postprocessor,
                     adapters=[], debug_logger=debug_logger)

    # ---- PlatformLauncher 管理所有平台 ----
    launcher = PlatformLauncher(config, bot_name="南瓜")
    adapters = await launcher.launch()
    bus.adapters = adapters

    print("[bot] Pipeline 就绪，多平台启动...\n")

    try:
        await launcher.start_all(bus.on_message)
    except KeyboardInterrupt:
        print("\n正在退出...")
    finally:
        await launcher.shutdown()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())

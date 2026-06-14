# 南瓜 Bot — CLAUDE.md

> 一个拟人化 AI 聊天 Bot。Pipeline 架构，DeepSeek API，SQLite 持久化。

## 项目结构

```
nan-gua-bot/
├── run.py                          # 入口脚本
├── config.yaml                     # 运行时配置
├── .env                            # DEEPSEEK_API_KEY
├── src/
│   ├── core/                       # 核心引擎（子项目 1）
│   │   ├── pipeline.py             #   MessageBus — 四阶段编排
│   │   ├── session.py              #   SessionManager — 用户解析 + 关系状态
│   │   ├── context.py              #   ContextAssembler — 五层 system prompt 拼装
│   │   ├── llm.py                  #   LLMEngine — API 调用 + Sidecar JSON + 重试
│   │   ├── postprocess.py          #   PostProcessor — 短句拆分 + Sidecar 编排
│   │   └── contracts.py            #   5 个 pipeline dataclass
│   ├── storage/                    # 持久化层
│   │   ├── models.py               #   所有 dataclass（User, Message, ...）
│   │   ├── db.py                   #   SQLite schema + 迁移 + init_db
│   │   └── queries.py              #   CRUD 操作
│   ├── memory/                     # 持久化与记忆（子项目 2）
│   │   ├── cold_index.py           #   冷记忆倒排索引
│   │   ├── recall_ranker.py        #   情感加权召回排序
│   │   ├── summary_writer.py       #   温记忆摘要 + 话题提取
│   │   └── loop_detector.py        #   情节检测（规则优先 + LLM 兜底）
│   ├── relationship/               # 关系状态机（子项目 3）
│   │   ├── familiarity.py          #   熟悉度计算 + 动态 LAYER4 规则
│   │   └── branch_detector.py      #   分支检测 + streak 漂移
│   ├── persona/                    # 人格加载
│   │   └── memory.py               #   SelfMemory — self.md 读取器
│   ├── proactive/                   # 主动消息系统（子项目 4）
│   │   ├── trigger_manager.py       #   6 种触发器 + 关系门控
│   │   └── dispatcher.py            #   Dispatcher ABC + TerminalDispatcher
│   └── social/                      # 社交模拟（子项目 5）
│       ├── characters.py            #   CharacterManager — 角色池管理
│       ├── arcs.py                  #   ArcStateMachine — 非线性叙事弧
│       ├── event_generator.py       #   EventGenerator — LLM 事件生成
│       └── scheduler.py             #   Scheduler — 时间+对话混合触发
└── evolution/                       # 人格进化（子项目 6）
    ├── engine.py                    #   EvolutionEngine — 触发检测+编排
    ├── reflector.py                 #   Reflector — 输入组装+LLM反思+校验
    └── writeback.py                 #   WriteBack — 写回+snapshot+CHANGELOG
├── gateway/                         # 多平台适配层（子项目 7）
│   ├── adapter.py                   #   Adapter ABC — 平台无关接口
│   ├── terminal_adapter.py          #   TerminalAdapter — CLI 终端
│   ├── wechat_adapter.py            #   WeChatAdapter — MCP 客户端
│   ├── mcp_client.py                #   MCPHttpClient — JSON-RPC 2.0
│   └── platform_launcher.py         #   PlatformLauncher — 多平台编排
├── tests/
│   ├── test_familiarity.py         # 13 tests
│   ├── test_branch_detector.py     # 14 tests
│   ├── test_pipeline.py
│   ├── test_mcp_client.py          # 7 tests (MCP 客户端)
│   ├── test_mcp_handler.py         # 7 tests (MCP handler)
│   ├── test_wechat_queue.py        # 6 tests (消息队列)
│   ├── test_wechat_protocol.py     # 5 tests (微信协议)
│   ├── test_adapter.py             # 3 tests (Adapter ABC)
│   ├── test_wechat_adapter.py      # 3 tests (WeChatAdapter)
│   ├── test_multi_platform_integration.py  # 16 tests (集成)
│   ├── test_integration.py         # 需要 DEEPSEEK_API_KEY
│   └── ...
├── data/                           # SQLite 数据库文件（gitignore）
└── wechat_mcp_server/               # 微信 MCP 独立进程（子项目 7）
    ├── server.py                    #   FastAPI + MCP 端点
    ├── mcp_handler.py               #   JSON-RPC 2.0 方法分发
    ├── wechat.py                    #   微信协议（XML/Token/客服API）
    ├── queue.py                     #   内存消息队列
    └── config.py                    #   公众号配置
```

## 架构：四阶段 Pipeline

```
MessageBus.on_message(user_id, platform, user_message)
    │
    ├─ Stage 1: SessionManager.resolve(user_id, platform)
    │     ├─ 从 DB 加载/创建 User
    │     ├─ 实时计算 familiarity_score（同步，当前轮生效）
    │     └─ 返回 UserSession(user, history, relationship, summary)
    │
    ├─ Stage 2: ContextAssembler.assemble(session, user_message)
    │     ├─ Layer 0: 人格核心（persona.md 逐层提取）
    │     ├─ Layer 1: 情感直觉
    │     ├─ Layer 2: 近期经历
    │     ├─ Layer 3: 冷记忆关联（ColdIndex.search）
    │     ├─ Layer 4: 关系行为规则（build_layer4_context，动态插值）
    │     └─ Layer 5: 元认知
    │     └─ 返回 PromptContext(system_prompt, messages, ...)
    │
    ├─ Stage 3: LLMEngine.chat(prompt_context)
    │     ├─ 调用 DeepSeek API
    │     ├─ 解析 Sidecar JSON（mood/deep_topic/worth_remembering/...）
    │     ├─ JSON 解析失败 → 规则兜底（不崩溃）
    │     └─ 返回 LLMResponse(reply_text, sidecar, ...)
    │
    └─ Stage 4: PostProcessor.run_sidecars(session, msg, response, system_prompt)
          ├─ worth_remembering → append_user_note（冷记忆写入）
          ├─ SummaryWriter.generate → insert_summary（温记忆写入）
          ├─ LoopDetector.detect → insert_open_loop（情节记忆写入）
          ├─ 分支检测 + streak 漂移（异步，下轮生效）
          └─ emotional_peaks 写入
```

## 核心约定

### 规则优先 + LLM 兜底
多个模块采用两层检测：规则快且免费，覆盖 80%；LLM 补剩下的 20%。
- `loop_detector.py` — 7 组关键词 → LLM.detect_open_loop
- `branch_detector.py` — 30 个信号词 → LLM 分类（边界 case）
- `llm.py` — JSON 解析失败 → 规则提取 mood/deep_topic

### 同步 vs 异步
- **同步**（当前轮生效）：familiarity 计算、LAYER4 规则生成
- **异步**（下轮生效）：分支检测、streak 漂移、摘要生成、冷记忆写入

### 关系状态机
- 6 个 RelationshipType：stranger → acquaintance → trusted → brother/respected/crush
- familiarity_score：4 因子加权（轮次 0.4 + 深度 0.3 + 深夜 0.2 + 主动 0.1），实时计算
- branch_signal_streak：±30 范围，streak≥5 切入分支，streak≤-10 回退 trusted
- 分支检测只在 trusted 阶段触发

### 五层 System Prompt
- Layer 0: 人格核心（语言风格、价值观、身份）
- Layer 1: 情感直觉（当前 mood、energy）
- Layer 2: 近期经历（life_events、self.md 叙事）
- Layer 3: 冷记忆（ColdIndex 关键词关联触发，最多 3 条）
- Layer 4: 关系行为规则（familiarity 动态插值 warmth/disclosure/swearing/initiative）
- Layer 5: 元认知（成长目标、自省触发）

## 子项目进度

| # | 子系统 | 状态 |
|---|--------|------|
| 1 | 核心引擎（Pipeline + 5 层 context + Sidecar） | ✅ 完成 |
| 2 | 持久化与记忆（ColdIndex + recall + summary + loop） | ✅ 完成 |
| 3 | 关系状态机（familiarity + branch + LAYER4 动态化） | ✅ 完成 |
| 4 | 主动消息系统（TriggerManager + Dispatcher） | ✅ 完成 |
| 5 | 社交模拟（CharacterManager + ArcStateMachine + Scheduler） | ✅ 完成 |
| 6 | 人格进化（EvolutionEngine + Reflector + WriteBack） | ✅ 完成 |
| 7 | 多平台适配 | ✅ 完成 |

## 禁止事项

- **不碰 `src/core/bot.py`** — 已被 pipeline.py 替代，废弃文件
- **不改 `src/core/style_detector.py`** — 被 branch_detector.py 替代
- **不删除 `src/core/llm.py` 中的 `generate_summary` / `detect_open_loop`** — 外部仍在调用
- **不在 session.py 的 resolve() 中做 DB 写入** — familiarity 只修改内存中的 user 对象

## 发布规定

- 每次发布版本前必须更新根目录 `VERSION`。
- 每次发布版本前必须更新根目录 `CHANGELOG.md`，使用 GitHub 常见的分点更新日志格式：
  - `## [x.y] - YYYY-MM-DD`
  - `### Added`
  - `### Changed`
  - `### Fixed`
  - `### Tests`
- 更新日志必须写清用户可感知变化、架构变化、修复项和验证结果。
- 版本 tag 使用 `vX.Y` 格式，例如 `v0.2`。

## 常用命令

```bash
# 运行所有单元测试（不需要 API key）
pytest tests/ -v --ignore=tests/test_integration.py

# 运行特定模块测试
pytest tests/test_familiarity.py -v
pytest tests/test_branch_detector.py -v

# 运行集成测试（需要 DEEPSEEK_API_KEY）
pytest tests/test_integration.py -v -m integration

# 启动 Bot
python run.py
```

## 技术栈

- Python 3.12
- aiosqlite（异步 SQLite）
- DeepSeek API（OpenAI 兼容）
- pytest + pytest-asyncio
- 纯数学 familiarity 计算（零外部依赖）

"""Tests for run.py wiring."""

import pytest


@pytest.mark.asyncio
async def test_main_wires_postprocessor_with_persona_inputs(monkeypatch, tmp_path):
    import run as run_module

    captured = {}
    config = {
        "storage": {"db_path": str(tmp_path / "bot.db"), "log_path": str(tmp_path / "logs")},
        "persona": {
            "persona_md_path": "data/persona.md",
            "self_md_path": "data/self.md",
        },
        "llm": {
            "model": "deepseek-chat",
            "max_tokens": 1024,
            "temperature": 0.8,
            "base_url": "https://api.deepseek.com",
        },
        "platforms": {"terminal": {"enabled": False}, "wechat": {"enabled": False}},
        "debug_level": 0,
    }

    class FakeDb:
        async def close(self):
            pass

    async def fake_init_db(path):
        return FakeDb()

    async def fake_get_active_users(conn):
        return []

    class FakePostProcessor:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        def set_proactive_sender(self, sender):
            captured["proactive_sender_set"] = sender

    class FakeLauncher:
        def __init__(self, config, bot_name):
            pass

        async def launch(self):
            return []

        async def start_all(self, on_message):
            return None

        async def shutdown(self):
            return None

    class FakeBus:
        def __init__(self, *args, **kwargs):
            self.adapters = []

        async def on_message(self, user_id, text):
            return None

        async def send_proactive(self, user_id, messages):
            return True

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(run_module.sys, "argv", ["run.py"])
    monkeypatch.setattr(run_module, "load_config", lambda path: config)
    monkeypatch.setattr(run_module, "init_db", fake_init_db)
    monkeypatch.setattr(run_module, "_get_active_users", fake_get_active_users)
    monkeypatch.setattr(run_module, "SelfMemory", lambda path: {"path": path})
    monkeypatch.setattr(run_module, "ContextAssembler", lambda *args, **kwargs: object())
    monkeypatch.setattr(run_module, "LLMEngine", lambda **kwargs: object())
    monkeypatch.setattr(run_module, "DebugLogger", lambda level: object())
    monkeypatch.setattr(run_module, "SummaryWriter", lambda llm: object())
    monkeypatch.setattr(run_module, "LoopDetector", lambda llm, db: object())
    monkeypatch.setattr(run_module, "SessionManager", lambda db: object())
    monkeypatch.setattr(run_module, "PostProcessor", FakePostProcessor)
    monkeypatch.setattr(run_module, "TerminalDispatcher", lambda db: object())
    monkeypatch.setattr(run_module, "MessageBus", FakeBus)
    monkeypatch.setattr(run_module, "PlatformLauncher", FakeLauncher)

    await run_module.main()

    assert captured["self_memory"] == {"path": "data/self.md"}
    assert captured["persona_path"] == "data/persona.md"
    assert captured["self_md_path"] == "data/self.md"
    assert captured["config"] is config

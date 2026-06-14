import os
from pathlib import Path

import yaml


def _load_wechat_config() -> dict:
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return config.get("platforms", {}).get("wechat", {}) or {}
    except Exception:
        return {}


_wechat_config = _load_wechat_config()


def _get_config_value(env_key: str, config_key: str, default: str) -> str:
    value = os.getenv(env_key)
    if value:
        return value
    value = _wechat_config.get(config_key)
    if value:
        return str(value)
    return default

WECHAT_APPID = _get_config_value("WECHAT_APPID", "appid", "wx_test_appid")
WECHAT_SECRET = _get_config_value("WECHAT_SECRET", "secret", "test_secret")
WECHAT_TOKEN = _get_config_value("WECHAT_TOKEN", "token", "test_token")
MCP_PORT = int(_get_config_value("MCP_PORT", "mcp_port", "8090"))

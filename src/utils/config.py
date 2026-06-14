"""config.yaml 加载器。"""

from pathlib import Path
from typing import Any

import yaml


_config: dict[str, Any] | None = None


def load_config(config_path: str | Path = "config.yaml") -> dict[str, Any]:
    """加载 YAML 配置文件。缓存结果，重复调用返回缓存。"""
    global _config
    if _config is not None:
        return _config

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f)

    _resolve_paths(_config, config_path.parent)
    return _config


def _resolve_paths(config: dict[str, Any], base_dir: Path) -> None:
    """将相对路径转为绝对路径。"""
    path_keys = [
        ("persona", "persona_md_path"),
        ("persona", "self_md_path"),
        ("persona", "skill_md_path"),
        ("storage", "db_path"),
        ("storage", "log_path"),
    ]
    for section, key in path_keys:
        if section in config and key in config[section]:
            p = Path(config[section][key])
            if not p.is_absolute():
                config[section][key] = str((base_dir / p).resolve())


def reload_config(config_path: str | Path = "config.yaml") -> dict[str, Any]:
    """重新加载配置（清除缓存）。"""
    global _config
    _config = None
    return load_config(config_path)


def get_config() -> dict[str, Any]:
    """获取已加载的配置。如未加载则自动加载。"""
    if _config is None:
        return load_config()
    return _config

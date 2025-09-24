"""配置持久化模块。

默认配置文件: config.json （位于运行目录）
"""
from __future__ import annotations
import json
import os
from typing import Any, Dict

DEFAULT_PATH = "config.json"
DEFAULT_CONFIG = {
    "ntrip": {
        "host": "",
        "port": 2101,
        "mountpoint": "",
        "username": "",
        "password": ""
    },
    "position": {
        "lat": 0.0,
        "lon": 0.0,
        "alt": 0.0
    },
    "serial": {
        "port": "",
        "baudrate": 57600
    }
}


def load_config(path: str = DEFAULT_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return json.loads(json.dumps(DEFAULT_CONFIG))  # 深拷贝
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 合并缺失字段
    def merge(d, tpl):
        for k, v in tpl.items():
            if k not in d:
                d[k] = v
            elif isinstance(v, dict):
                merge(d[k], v)
    merge(data, DEFAULT_CONFIG)
    return data


def save_config(cfg: Dict[str, Any], path: str = DEFAULT_PATH):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

__all__ = ["load_config", "save_config", "DEFAULT_CONFIG"]

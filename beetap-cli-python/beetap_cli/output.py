"""输出约定:数据 → stdout,进度/错误 → stderr(前缀 [beetap-cli])。

`-f json` 时 stdout 只输出一行完整信封 JSON,便于机器解析;text 模式下
各命令输出人类可读内容(截图/节点第一行仍是本机文件路径)。
"""

from __future__ import annotations

import json
import sys

_JSON_MODE = False


def configure(json_mode: bool) -> None:
    global _JSON_MODE
    _JSON_MODE = bool(json_mode)


def json_mode() -> bool:
    return _JSON_MODE


def emit_json(envelope: dict) -> None:
    """stdout 输出一行完整信封对象(字段名即插件端点字段)。"""
    print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))


def data(text: str = "") -> None:
    """数据输出:text 模式写 stdout,json 模式静默(避免污染机器输出)。"""
    if not _JSON_MODE:
        print(text)


def info(text: str) -> None:
    """进度/说明信息,始终写 stderr。"""
    print(f"[beetap-cli] {text}", file=sys.stderr)


def error(text: str) -> None:
    print(f"[beetap-cli] 错误: {text}", file=sys.stderr)


def warn(text: str) -> None:
    print(f"[beetap-cli] 警告: {text}", file=sys.stderr)


def kv(label: str, value: str, label_width: int = 8) -> None:
    data(f"{label.ljust(label_width)}{value}")


def emit_log_line(log: dict) -> None:
    """monitor 的日志输出:json 模式逐行 JSONL,text 模式原样。"""
    if _JSON_MODE:
        payload = {
            "seq": log.get("seq"),
            "level": log.get("level"),
            "time": log.get("time"),
            "text": log.get("text", ""),
        }
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        print(log.get("text", ""))

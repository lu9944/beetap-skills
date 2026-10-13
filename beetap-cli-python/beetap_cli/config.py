"""配置解析:命令行参数 > 环境变量 > .env 文件 > 默认值。

支持的键(环境变量与同名 .env 键):

| 键 | 默认 | 说明 |
|---|---|---|
| `BEETAP_URL` | `http://127.0.0.1:9318` | 插件控制端点(协议 v1 第 2 节) |
| `BEETAP_MODULE` | 自动 | BeeTap 工程名或路径(多工程时必填) |
| `BEETAP_TIMEOUT` | `360s` | 单次命令的 HTTP 超时(如 `6m` / `360s`;必须大于各请求的 timeoutMs) |

设备连接自协议 v1(插件 1.3.10+)起只能在 IDEA 插件里操作,CLI 不再有连接参数。
.env 查找顺序:`--env <path>` → 当前目录 `.env` → 技能根目录 `.env`
(不含任何已知键的文件,如空文件,会被跳过)。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import CliError, EXIT_USAGE

ENV_URL = "BEETAP_URL"
ENV_MODULE = "BEETAP_MODULE"
ENV_TIMEOUT = "BEETAP_TIMEOUT"

# 已知键集合:查找 .env 时,不含任何已知键的文件(如空文件)会被跳过
KNOWN_ENV_KEYS = frozenset({ENV_URL, ENV_MODULE, ENV_TIMEOUT})

DEFAULT_URL = "http://127.0.0.1:9318"
DEFAULT_TIMEOUT = 360.0  # 官方 CLI 默认 6m;run --wait 长脚本用 --timeout 加大

# 技能根目录(bin/、beetap_cli/ 的上级)
SKILL_ROOT = Path(__file__).resolve().parent.parent

_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h)?")
_DURATION_UNIT = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def parse_duration(text: str, *, default_unit: str = "s") -> float:
    """解析时长文本,返回秒。支持 20s / 500ms / 1.5m / 1h / 1m30s / 90(裸数字按 default_unit)。

    非法输入抛 ValueError(由 argparse 或调用方转成用法错误)。
    """
    raw = str(text).strip()
    if not raw:
        raise ValueError("时长不能为空")
    total = 0.0
    pos = 0
    for match in _DURATION_RE.finditer(raw):
        if match.start() != pos:
            raise ValueError(f"无法解析时长: {text}")
        value = float(match.group(1))
        unit = match.group(2) or default_unit
        total += value * _DURATION_UNIT[unit]
        pos = match.end()
    if pos != len(raw):
        raise ValueError(f"无法解析时长: {text}")
    return total


def duration_arg(text: str) -> float:
    """argparse 的 type 回调:把 5m / 20s / 1h 解析为秒。"""
    try:
        value = parse_duration(text)
    except ValueError as exc:
        raise argparse_type_error(str(exc)) from exc
    if value <= 0:
        raise argparse_type_error("时长必须大于 0")
    return value


def argparse_type_error(message: str):
    import argparse

    return argparse.ArgumentTypeError(message)


def env_search_paths() -> list[Path]:
    paths = [Path.cwd() / ".env"]
    skill_env = SKILL_ROOT / ".env"
    if skill_env != paths[0]:
        paths.append(skill_env)
    return paths


def parse_env_file(path: Path) -> dict[str, str]:
    """解析 dotenv 格式文件(支持注释、export 前缀与单双引号)。"""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"读取 .env 文件失败: {path}: {exc}", EXIT_USAGE) from exc
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if value[:1] in ("'", '"'):
            quote = value[0]
            end = value.find(quote, 1)
            if end > 0:
                value = value[1:end]
            else:
                value = value[1:]
        else:
            inline = value.find(" #")
            if inline >= 0:
                value = value[:inline].rstrip()
        values[key] = value
    return values


def find_env_file(explicit: str | None = None) -> Path | None:
    """查找 .env:--env 指定 → 当前目录 → 技能根目录。

    跳过不含任何已知键的文件(空文件、只写别的工具配置的 .env 不会遮蔽后面的配置);
    若都不含已知键,则返回第一个存在的文件供诊断展示。
    """
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.exists() else None
    first_existing: Path | None = None
    for candidate in env_search_paths():
        if not candidate.exists():
            continue
        if first_existing is None:
            first_existing = candidate
        try:
            values = parse_env_file(candidate)
        except CliError:
            return candidate  # 读取失败时保留,由 load 报告具体错误
        if any(key in KNOWN_ENV_KEYS for key in values):
            return candidate
    return first_existing


@dataclass
class Config:
    url: str = DEFAULT_URL
    module: str | None = None
    timeout: float = DEFAULT_TIMEOUT
    env_file: Path | None = None


def load(
    url: str | None = None,
    module: str | None = None,
    timeout: float | None = None,
    env_file: str | None = None,
) -> Config:
    path = find_env_file(env_file)
    values = parse_env_file(path) if path else {}

    resolved_url = (
        url or os.environ.get(ENV_URL) or values.get(ENV_URL) or DEFAULT_URL
    ).strip()
    resolved_module = (module or os.environ.get(ENV_MODULE) or values.get(ENV_MODULE) or "").strip() or None

    resolved_timeout = timeout
    if resolved_timeout is None:
        raw = os.environ.get(ENV_TIMEOUT) or values.get(ENV_TIMEOUT)
        if raw:
            try:
                resolved_timeout = parse_duration(raw)
            except ValueError as exc:
                raise CliError(
                    f"{ENV_TIMEOUT} 非法: {raw}({exc})", EXIT_USAGE
                ) from exc
    if not resolved_timeout or resolved_timeout <= 0:
        resolved_timeout = DEFAULT_TIMEOUT

    if not resolved_url.startswith(("http://", "https://")):
        raise CliError(
            f"端点地址必须以 http:// 或 https:// 开头: {resolved_url}", EXIT_USAGE
        )
    return Config(
        url=resolved_url.rstrip("/"),
        module=resolved_module,
        timeout=float(resolved_timeout),
        env_file=path,
    )

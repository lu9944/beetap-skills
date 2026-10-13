"""状态 / 工程 / 日志 / 原始调用命令。

- status / projects:GET /status、GET /projects
- logs:GET /logs 增量拉取(打印 cursor,供下次 --since 使用)
- monitor:循环 GET /logs 跟随日志,-k 命中退出 0,超时退出 2
  (协议 §7:起点用 /logs?since=0&lines=1 取当前 cursor,关键字忽略大小写子串匹配)
- raw:任意端点透传(调试与未来接口兜底)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from . import output
from .client import BeeTapClient, require_ok
from .config import Config
from .errors import CliError, EXIT_TIMEOUT, EXIT_USAGE, plugin_exit

DEFAULT_STOP_KEYWORD = "脚本已停止运行"
MONITOR_POLL_INTERVAL = 0.5


class App:
    """命令上下文:配置 + HTTP 客户端。"""

    def __init__(self, config: Config, client: BeeTapClient) -> None:
        self.config = config
        self.client = client

    def module(self, args_module: str | None) -> str | None:
        return args_module or self.config.module


# ----------------------------------------------------------------------
# status / projects
# ----------------------------------------------------------------------


def cmd_status(args, app: App) -> int:
    envelope = app.client.get("/status")
    data = require_ok(envelope)
    if output.json_mode():
        output.emit_json(envelope)
        return 0

    device = data.get("device") or {}
    projects = data.get("projects") or []
    version = data.get("pluginVersion") or "未知"
    cli_port = data.get("cliPort")
    capture = data.get("captureMode") or ""
    output.kv("插件", f"BeeTap {version}  cliPort={cli_port}  captureMode={capture}")
    output.kv("端点", app.config.url)
    if device.get("connected"):
        model = device.get("model") or "未知机型"
        brand = device.get("brand") or ""
        android = device.get("androidVersion") or ""
        app_version = device.get("appVersion") or ""
        serial = device.get("serial") or ""
        mode = device.get("mode") or ""
        head = f"{model} ({brand} / {android})" if brand else f"{model} ({android})"
        output.kv("设备", f"已连接  {head}  app={app_version}  serial={serial}  mode={mode}")
    else:
        output.kv("设备", "未连接(在 IDEA 插件里点「USB 调试」/「WiFi 直连」;可用 beetap-cli connect --wait 等待)")
    if projects:
        output.kv("工程", f"{len(projects)} 个:")
        for item in projects:
            name = item.get("name") or item.get("projectName") or "?"
            path = item.get("path") or ""
            output.data(f"        - {name}  {path}")
    else:
        output.kv("工程", "未找到(在 IDEA 中打开 BeeTap 工程)")
    return 0


def cmd_projects(args, app: App) -> int:
    envelope = app.client.get("/projects")
    data = require_ok(envelope)
    if output.json_mode():
        output.emit_json(envelope)
        return 0
    projects = data.get("projects") or []
    if not projects:
        output.data("未找到 BeeTap 工程(在 IDEA 中打开工程,或确认插件已加载)")
        return 0
    for item in projects:
        name = item.get("name") or item.get("projectName") or "?"
        path = item.get("path") or ""
        output.data(f"{name}\t{path}")
    return 0


# ----------------------------------------------------------------------
# logs / monitor
# ----------------------------------------------------------------------


def cmd_logs(args, app: App) -> int:
    params: dict = {"since": args.since, "lines": args.lines}
    if args.project:
        params["project"] = args.project
    envelope = app.client.get("/logs", params)
    data = require_ok(envelope)
    if output.json_mode():
        output.emit_json(envelope)
        return 0
    logs = data.get("logs") or []
    for log in logs:
        output.emit_log_line(log)
    output.data(f"cursor={data.get('cursor')} count={len(logs)}")
    return 0


def current_cursor(app: App) -> int:
    """取当前最新日志游标(monitor 起点,避免捞历史日志)。

    协议 §7:GET /logs?since=0&lines=1 即返回当前 cursor。
    """
    data = require_ok(app.client.get("/logs", {"since": 0, "lines": 1}))
    try:
        return int(data.get("cursor") or 0)
    except (TypeError, ValueError):
        return 0


def split_keywords(values: list[str] | None) -> list[str]:
    """把 -k 的多次传参与 'a|||b' 分隔写法展开为关键字列表(去重保序)。"""
    result: list[str] = []
    for value in values or []:
        for part in str(value).split("|||"):
            part = part.strip()
            if part and part not in result:
                result.append(part)
    return result


def cmd_monitor(args, app: App) -> int:
    keywords = split_keywords(args.stop_on) or [DEFAULT_STOP_KEYWORD]
    lowered = [keyword.lower() for keyword in keywords]
    cursor = 0 if args.initial else current_cursor(app)
    deadline = time.monotonic() + args.max_duration
    while True:
        envelope = app.client.get("/logs", {"since": cursor, "lines": args.lines})
        data = require_ok(envelope)
        hit = None
        for log in data.get("logs") or []:
            output.emit_log_line(log)
            text = (log.get("text") or "").lower()
            for keyword, needle in zip(keywords, lowered):
                if needle in text:
                    hit = keyword
        cursor = int(data.get("cursor") or cursor)
        if hit is not None:
            output.info(f"命中关键字: {hit}")
            return 0
        if time.monotonic() >= deadline:
            output.error(
                f"monitor 超时({args.max_duration:g}s)未命中任何关键字: {' | '.join(keywords)}"
            )
            return EXIT_TIMEOUT
        time.sleep(MONITOR_POLL_INTERVAL)


# ----------------------------------------------------------------------
# raw 透传
# ----------------------------------------------------------------------


def _read_body_file(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CliError(f"读取 --body-file 失败: {exc}", EXIT_USAGE) from exc


def cmd_raw(args, app: App) -> int:
    method = args.method.upper()
    if method not in ("GET", "POST"):
        raise CliError(f"raw 只支持 GET / POST,收到 {method}", EXIT_USAGE)
    path = args.path
    if not path.startswith("/"):
        path = "/" + path

    body_text = args.body
    if args.body_file:
        if body_text:
            raise CliError("--body 与 --body-file 只能二选一", EXIT_USAGE)
        body_text = _read_body_file(args.body_file)
    body = None
    if body_text and body_text.strip():
        try:
            body = json.loads(body_text)
        except ValueError as exc:
            raise CliError(f"--body 不是合法 JSON: {exc}", EXIT_USAGE) from exc
    if method == "GET":
        if body is not None:
            raise CliError("GET 不支持请求体(--body)", EXIT_USAGE)
        envelope = app.client.get(path)
    else:
        envelope = app.client.post(path, body if isinstance(body, dict) else {})

    if output.json_mode():
        output.emit_json(envelope)
    else:
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    return plugin_exit(int(envelope.get("code") or 0))


# ----------------------------------------------------------------------
# 未使用但保留:显式文档化的导出
# ----------------------------------------------------------------------

__all__ = [
    "App",
    "cmd_status",
    "cmd_projects",
    "cmd_logs",
    "cmd_monitor",
    "cmd_raw",
    "current_cursor",
    "split_keywords",
    "DEFAULT_STOP_KEYWORD",
]

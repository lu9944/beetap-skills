"""设备连接(引导)与脚本运行控制。

协议 v1(插件 1.3.10+)起:
- 设备连接只能在 IDEA 插件 UI 完成,CLI 的 `/connect` 已禁用(恒返 1001);
  本 CLI 的 `connect` 命令只做「查看状态 + 可选等待 + 连接指引」,不再 POST /connect;
- run:POST /run 编译下发工程或脚本片段,默认等待结束并回显日志;
  `templatePath` 按协议必须位于解析到的 BeeTap 工程目录内,外部模板自动复制进工程(见 project.py);
- stop / pause / resume:POST /stop|/pause|/resume;stop 带 module 用于复位运行会话。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from . import output
from .client import require_ok
from .commands import App
from .errors import CliError, EXIT_BUSY, EXIT_NO_DEVICE, EXIT_TIMEOUT, EXIT_USAGE
from .project import ensure_template_in_project

JS_ERROR_MARKER = "JS 执行异常"
BUSY_MARKER = "BUSY"
CONNECT_POLL_INTERVAL = 1.0

# 服务端 /run timeoutMs 钳位区间(协议 §5.7:[5000, 1800000] ms)
WAIT_TIMEOUT_MIN = 5.0
WAIT_TIMEOUT_MAX = 1800.0

CONNECT_GUIDANCE = [
    "设备连接只能在 IDEA 插件里完成(协议 v1 / 插件 1.3.10+ 起 /connect 已禁用,恒返 1001);",
    "在 IDEA 的 BeeTap 插件里点「USB 调试」(或 WiFi 直连)完成连接;",
    "手机端调试 App 缺失时,用插件菜单安装(如「手机扫码安装调试 APK」);",
    "连接完成后可用 beetap-cli status 复核,或 beetap-cli connect --wait 等待。",
]


# ----------------------------------------------------------------------
# connect(仅查看/等待,连接动作在 IDEA 插件里)
# ----------------------------------------------------------------------


def cmd_connect(args, app: App) -> int:
    legacy = [
        name
        for name, value in (
            ("--mode", getattr(args, "mode", None)),
            ("--serial", getattr(args, "serial", None)),
            ("--host", getattr(args, "host", None)),
            ("--port", getattr(args, "port", None)),
        )
        if value is not None
    ]
    if legacy:
        output.warn(
            "已忽略设备连接参数(" + ", ".join(legacy) + "):"
            "协议 v1 起 /connect 已禁用,连接只能在 IDEA 插件里操作"
        )

    envelope = app.client.get("/status")
    data = require_ok(envelope)
    device = data.get("device") or {}
    wait = getattr(args, "wait", 0.0) or 0.0

    if not device.get("connected") and wait > 0:
        output.info(
            f"等待设备连接(最长 {wait:g}s):请在 IDEA 插件里点「USB 调试」/「WiFi 直连」..."
        )
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            time.sleep(CONNECT_POLL_INTERVAL)
            envelope = app.client.get("/status")
            data = require_ok(envelope)
            device = data.get("device") or {}
            if device.get("connected"):
                break

    if not device.get("connected"):
        message = "等待设备连接超时" if wait > 0 else "设备未连接"
        raise CliError(message, EXIT_NO_DEVICE, CONNECT_GUIDANCE)

    if output.json_mode():
        output.emit_json(envelope)
        return 0
    model = device.get("model") or "未知机型"
    android = device.get("androidVersion") or ""
    app_version = device.get("appVersion") or ""
    serial = device.get("serial") or ""
    mode = device.get("mode") or ""
    output.data(
        f"已连接: {model} ({android})  app={app_version}  serial={serial}  mode={mode}"
    )
    return 0


# ----------------------------------------------------------------------
# run
# ----------------------------------------------------------------------


def read_code_source(path: str) -> str:
    """读取 --code 的脚本片段文件;`-` 表示标准输入。"""
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CliError(f"读取 --code 脚本失败: {exc}", EXIT_USAGE) from exc


def clamp_wait_timeout(seconds: float) -> tuple[float, str | None]:
    """把 --wait-timeout 钳位到服务端区间 [5s, 30m],返回 (值, 提示文本或 None)。"""
    if seconds < WAIT_TIMEOUT_MIN:
        return WAIT_TIMEOUT_MIN, f"--wait-timeout 小于服务端下限,已按 {WAIT_TIMEOUT_MIN:g}s 计算"
    if seconds > WAIT_TIMEOUT_MAX:
        return (
            WAIT_TIMEOUT_MAX,
            f"--wait-timeout 超过服务端上限,已按 {WAIT_TIMEOUT_MAX / 60:g}m 计算",
        )
    return seconds, None


def build_run_body(
    *,
    module: str | None,
    wait: bool,
    wait_timeout: float,
    keywords: list[str] | None = None,
    code: str | None = None,
    snippet: str | None = None,
    template: str | None = None,
) -> dict:
    if code is not None and snippet is not None:
        raise CliError("--code 与 --snippet 只能二选一", EXIT_USAGE)
    body: dict = {}
    if module:
        body["module"] = module
    if code is not None:
        body["code"] = code
    if snippet is not None:
        body["code"] = snippet
    if template:
        if "code" not in body:
            raise CliError("--template 仅在 --code/--snippet 片段模式下有效", EXIT_USAGE)
        body["templatePath"] = template
    if wait:
        body["wait"] = True
        body["timeoutMs"] = int(wait_timeout * 1000)
    else:
        body["wait"] = False
    if keywords:
        body["keywords"] = list(keywords)
    return body


def find_js_error(logs: list[dict]) -> str | None:
    """JS 运行期错误不会产生 HTTP 错误码,需从日志中识别。"""
    for log in logs or []:
        text = log.get("text") or ""
        if JS_ERROR_MARKER in text:
            return text
    return None


def find_busy(logs: list[dict]) -> str | None:
    """设备端已有脚本运行时以 BUSY 日志拒绝,最终 stopReason=timeout(HTTP code 仍为 0)。"""
    for log in logs or []:
        text = log.get("text") or ""
        if BUSY_MARKER in text:
            return text
    return None


def cmd_run(args, app: App) -> int:
    from .commands import split_keywords

    code = read_code_source(args.code) if args.code else None
    keywords = split_keywords(args.stop_on)
    wait = args.wait
    wait_timeout = args.wait_timeout
    if wait:
        wait_timeout, clamp_note = clamp_wait_timeout(wait_timeout)
        if clamp_note:
            output.warn(clamp_note)

    template = args.template
    if template:
        if code is None and args.snippet is None:
            raise CliError("--template 仅在 --code/--snippet 片段模式下有效", EXIT_USAGE)
        template = ensure_template_in_project(app.client, app.module(args.module), template)

    body = build_run_body(
        module=app.module(args.module),
        wait=wait,
        wait_timeout=wait_timeout,
        keywords=keywords,
        code=code,
        snippet=args.snippet,
        template=template,
    )
    # wait=true 时 HTTP 超时必须大于请求的 timeoutMs,否则本地先超时、脚本还在手机上跑
    http_timeout = max(app.config.timeout, wait_timeout + 30) if wait else app.config.timeout
    envelope = app.client.post("/run", body, timeout=http_timeout)
    data = require_ok(envelope)
    if output.json_mode():
        output.emit_json(envelope)

    logs = data.get("logs") or []
    if not output.json_mode():
        for log in logs:
            output.emit_log_line(log)
        stop = data.get("stopReason") or "unknown"
        message = data.get("message") or ""
        duration = data.get("durationMs")
        summary = f"stop={stop}"
        if duration is not None:
            summary += f" durationMs={duration}"
        if message:
            summary += f" message={message}"
        output.data(summary)

    js_error = find_js_error(logs)
    if js_error:
        output.warn(f"日志出现 {JS_ERROR_MARKER}(HTTP code=0,但脚本未成功): {js_error}")

    busy = find_busy(logs)
    if busy:
        output.error("设备端已有脚本在运行(busy),先 stop 再重试")
        return EXIT_BUSY

    stop_reason = data.get("stopReason")
    if stop_reason == "timeout":
        output.error("run 等待超时,脚本可能仍在手机运行;可用 logs 继续拉取,或 stop 停止")
        return EXIT_TIMEOUT
    if stop_reason == "disconnected":
        output.warn("设备在运行期间断开连接(协议 stopReason=disconnected);请重新连接后复核结果")
    return 0


# ----------------------------------------------------------------------
# stop / pause / resume
# ----------------------------------------------------------------------


ACTION_LABELS = {"stop": "停止", "pause": "暂停", "resume": "继续"}


def cmd_signal(action: str):
    """生成 stop / pause / resume 的命令实现(共用同一路径逻辑)。

    协议 §5.8:请求 `{"module": "可选"}`;module 仅被 /stop 用于复位运行会话状态,
    /pause、/resume 忽略一切参数;指令是发后即忘的。
    """

    def run(args, app: App) -> int:
        body: dict = {}
        if action == "stop":
            module = app.module(args.module)
            if module:
                body["module"] = module
        envelope = app.client.post(f"/{action}", body)
        require_ok(envelope)
        if output.json_mode():
            output.emit_json(envelope)
        else:
            output.data(f"已发送{ACTION_LABELS[action]}指令(发后即忘,不代表脚本已{ACTION_LABELS[action]})")
        return 0

    return run

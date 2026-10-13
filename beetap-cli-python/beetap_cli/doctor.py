"""环境体检:Python 版本、配置、插件连通性、工程解析、设备连接、工程能力。

任何设备操作前先跑 `beetap-cli doctor`。设备连接自协议 v1(插件 1.3.10+)起
只能在 IDEA 插件 UI 完成,CLI 不提供连接动作;体检会给出手把手指引。
体检按阻塞问题返回退出码(5/4/1),全部通过返回 0。
"""

from __future__ import annotations

import sys
from pathlib import Path

from .client import require_ok
from .commands import App
from .config import ENV_MODULE, ENV_TIMEOUT, ENV_URL
from .errors import CliError, EXIT_NO_DEVICE, EXIT_UNREACHABLE, EXIT_USAGE
from .device import CONNECT_GUIDANCE

TOTAL = 6


def _step(index: int, title: str, ok: bool | None, detail: str) -> None:
    mark = "通过" if ok else ("提示" if ok is None else "失败")
    print(f"[{index}/{TOTAL}] {title} ... {mark} ({detail})")


def _guidance(lines: list[str]) -> None:
    for line in lines:
        print(f"    - {line}")


def _resolve_project(projects: list[dict], module: str | None) -> tuple[dict | None, str]:
    """在工程列表里解析 -m/--module;返回 (工程, 说明)。"""
    if module:
        for item in projects:
            if module in (item.get("name"), item.get("path"), item.get("projectName")):
                return item, f"{item.get('name')}"
        return None, f"未找到与 -m {module} 匹配的工程"
    if len(projects) == 1:
        return projects[0], str(projects[0].get("name"))
    if not projects:
        return None, "IDEA 中未找到 BeeTap 工程"
    return None, f"有 {len(projects)} 个工程,需用 -m 指定"


def _find_toml(project: dict | None) -> Path | None:
    candidates = []
    if project and project.get("path"):
        candidates.append(Path(str(project["path"])))
    candidates.append(Path.cwd())
    for base in candidates:
        toml = base / "BeeTap.toml"
        if toml.exists():
            return toml
    return None


def _toml_capabilities(toml_path: Path) -> dict[str, str]:
    """读取 BeeTap.toml 的 [plugin] 能力开关(无需第三方库,逐行解析)。"""
    capabilities: dict[str, str] = {}
    in_plugin = False
    try:
        text = toml_path.read_text(encoding="utf-8")
    except OSError:
        return capabilities
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("["):
            in_plugin = line.replace(" ", "") == "[plugin]"
            continue
        if in_plugin and "=" in line:
            key, _, value = line.partition("=")
            capabilities[key.strip()] = value.strip().strip('"').strip("'")
    return capabilities


def doctor(args, app: App) -> int:
    print(f"BeeTap CLI 环境检查 (端点: {app.config.url})\n")
    blocking: list[int] = []  # 收集阻塞问题的退出码,取第一个

    # 1. Python 版本
    version = ".".join(str(v) for v in sys.version_info[:3])
    ok1 = sys.version_info >= (3, 9)
    _step(1, "Python 版本", ok1, version)
    if not ok1:
        blocking.append(EXIT_USAGE)
        _guidance(["需要 Python 3.9+(仅标准库,无第三方依赖)。"])

    # 2. 配置
    env_file = app.config.env_file or "(未找到 .env,使用默认值/环境变量)"
    module = app.module(args.module) or "(自动)"
    _step(
        2,
        "配置项",
        True,
        f"URL={app.config.url}, MODULE={module}, "
        f"TIMEOUT={app.config.timeout:g}s, .env={env_file}",
    )
    _guidance(
        [
            f"可用的环境变量/.env 键: {ENV_URL} / {ENV_MODULE} / {ENV_TIMEOUT};",
            "多工程时用 -m/--module 指定工程名或路径;",
            "设备连接由 IDEA 插件负责(协议 v1 起 CLI /connect 已禁用),无需任何连接配置。",
        ]
    )

    # 3. 插件控制端点连通性
    try:
        status_envelope = app.client.get("/status")
        status_data = require_ok(status_envelope)
    except CliError as exc:
        _step(3, "插件控制端点", False, exc.message)
        blocking.append(exc.exit_code or EXIT_UNREACHABLE)
        _guidance(exc.guidance or [
            "确认 IntelliJ IDEA 已启动,且已打开含 BeeTap 工程的项目;",
            "确认端口未被 -Dbeetap.cliPort 改过(默认 9318),用 -u/--url 同步。",
        ])
        print("\n环境检查未通过:插件不可达,后续检查已跳过。")
        return blocking[0]

    port = status_data.get("cliPort")
    _step(3, "插件控制端点", True, f"HTTP 可达,cliPort={port}")

    # 4. 插件版本与工程解析
    plugin_version = status_data.get("pluginVersion") or "未知"
    projects = status_data.get("projects") or []
    project, detail = _resolve_project(projects, app.module(args.module))
    ok4 = project is not None
    if not projects:
        detail = "未找到 BeeTap 工程(请在 IDEA 中打开工程)"
    _step(4, "工程解析", ok4, f"插件 {plugin_version}, {detail}")
    if not ok4:
        blocking.append(EXIT_USAGE)
        _guidance(
            [
                "运行 beetap-cli projects 查看当前打开的工程;",
                "多工程时用 -m/--module 指定(工程目录名或绝对路径)。",
            ]
        )

    # 5. 设备连接(连接动作在 IDEA 插件里完成;CLI 只查看/等待)
    device = status_data.get("device") or {}
    if device.get("connected"):
        model = device.get("model") or "未知机型"
        android = device.get("androidVersion") or ""
        serial = device.get("serial") or ""
        mode = device.get("mode") or ""
        _step(
            5,
            "设备连接",
            True,
            f"{model} ({android}) app={device.get('appVersion')} serial={serial} mode={mode}",
        )
    else:
        _step(5, "设备连接", False, "未连接(请按下面指引在 IDEA 插件里连接)")
        blocking.append(EXIT_NO_DEVICE)
        _guidance(
            CONNECT_GUIDANCE
            + [
                "连接过程可在终端等待:beetap-cli connect --wait 60s(连接成功后自动返回)。",
            ]
        )

    # 6. 工程能力(BeeTap.toml,提示性)
    toml_path = _find_toml(project)
    if toml_path:
        caps = _toml_capabilities(toml_path)
        if caps:
            summary = ", ".join(f"{k}={v}" for k, v in caps.items())
            disabled_ocr = any(
                caps.get(key, "否") in ("否", "false", "False")
                for key in ("includeMlKitOcr", "includePaddleOcr")
            )
            _step(
                6,
                "工程能力",
                None,
                f"{toml_path.name}: {summary}",
            )
            if disabled_ocr:
                _guidance(
                    [
                        "OCR 能力(includeMlKitOcr/includePaddleOcr)为「否」时 /ocr 会返回 result=null;",
                        "需要 OCR 时先在 BeeTap.toml 打开对应能力并重新打包 App。",
                    ]
                )
        else:
            _step(6, "工程能力", None, f"{toml_path} 未解析到 [plugin] 配置")
    else:
        _step(6, "工程能力", None, "未找到 BeeTap.toml(跳过)")

    print()
    if blocking:
        print(f"环境检查未全部通过(退出码 {blocking[0]}),请按上面提示修复后重试。")
        return blocking[0]
    print("环境检查全部通过,可以开始使用:")
    print("  beetap-cli status                     查看插件/设备/工程状态")
    print("  beetap-cli run                        编译并运行工程(等待结束、回显日志)")
    print("  beetap-cli screenshot && beetap-cli nodes   先取证再写脚本")
    print("  beetap-cli monitor -k '关键字'         跟随日志等待标记")
    return 0

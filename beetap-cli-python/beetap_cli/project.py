"""工程解析与模板图落位(协议 v1 §5.7 / §5.10 / §8)。

协议要求 `/run` 的 `templatePath`(code 模式)与 `/test-image` findpic 的
`templatePath` **必须位于解析到的 BeeTap 工程目录内**(越界 → 1001,1.3.10 起)。
本模块在**需要下发模板图时**才查询 `GET /status` 解析工程目录:
- 模板已在工程目录内 → 原样使用;
- 否则复制到 `<工程>/bt_work_temp/android/beetap_cli_template.<ext>` 后再提交;
- 解析不到工程(未打开/多工程未指定 -m) → 原样提交,由服务端按协议报错。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import output
from .client import BeeTapClient, require_ok
from .errors import CliError, EXIT_FAILURE, EXIT_USAGE

TEMPLATE_FILENAME_STEM = "beetap_cli_template"


def pick_project_path(projects: list[dict], module: str | None) -> str | None:
    """按协议从 /status 的工程列表里解析工程目录。

    module 匹配:工程目录名(name)/ BeeTap.toml 工程名(projectName)/ 绝对路径(path),
    均大小写不敏感。未传 module 时仅当恰好一个工程才取它。
    """
    if module:
        key = str(module).strip().rstrip("/\\").lower()
        if not key:
            return None
        for item in projects:
            name = str(item.get("name") or "").lower()
            project_name = str(item.get("projectName") or "").lower()
            path = str(item.get("path") or "")
            if key in (name, project_name) or (path and key == path.rstrip("/\\").lower()):
                return path or None
        return None
    if len(projects) == 1:
        return str(projects[0].get("path") or "") or None
    return None


def resolve_project_dir(client: BeeTapClient, module: str | None) -> str | None:
    """GET /status 并解析工程目录;解析不到返回 None。"""
    data = require_ok(client.get("/status"))
    return pick_project_path(data.get("projects") or [], module)


def ensure_template_in_project(
    client: BeeTapClient, module: str | None, template: str
) -> str:
    """确保模板图位于工程目录内,返回可提交给插件的路径。

    已在工程目录内 → 原样返回;否则复制进 `<工程>/bt_work_temp/android/` 后返回副本路径。
    """
    source = Path(template).expanduser()
    if not source.exists():
        raise CliError(f"模板图不存在: {template}", EXIT_USAGE)

    project_dir = resolve_project_dir(client, module)
    if not project_dir:
        output.warn(
            "未能从 /status 解析工程目录;模板路径原样提交"
            "(协议要求模板必须位于 BeeTap 工程目录内,越界插件会返回 1001)"
        )
        return str(source)

    base = Path(project_dir)
    if not base.is_dir():
        output.warn(f"工程目录不存在: {base};模板路径原样提交")
        return str(source)

    try:
        source.resolve().relative_to(base.resolve())
        return str(source)
    except ValueError:
        pass

    suffix = source.suffix if source.suffix else ".png"
    target_dir = base / "bt_work_temp" / "android"
    target = target_dir / f"{TEMPLATE_FILENAME_STEM}{suffix}"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    except OSError as exc:
        raise CliError(f"复制模板图到工程目录失败: {exc}", EXIT_FAILURE) from exc
    output.info(f"模板图已复制进工程目录(协议要求模板位于工程目录内): {target}")
    # 保留 /status 返回的工程路径原样(不 resolve 符号链接,避免与服务端的包含判断不一致)
    return str(target)

"""取证命令:截图 / 节点树 / 节点参数 / OCR / 图色测试。

共同点:结果(图 + XML)落盘在**本机**插件临时目录,接口只返回路径;
`-o/--out`、`--dir` 可把文件另存到项目内,方便后续读取与入库。

协议 v1 要点:findpic 的模板图必须位于解析到的 BeeTap 工程目录内(越界 1001),
本 CLI 会把外部模板自动复制进工程(见 project.py);/test-image、/ocr 的 result
是 JSON 文本,需要二次解析(协议 §6 BT_RESULT)。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import nodes as node_tree
from . import output
from .client import require_ok
from .commands import App
from .errors import CliError, EXIT_FAILURE, EXIT_USAGE
from .project import ensure_template_in_project

OCR_TYPES = ("mlkit", "mlkitChinese", "mlkitLatin", "paddleOcrV4", "paddleOcrV5")
TEST_IMAGE_METHODS = ("findcolor", "findmulticolor", "cmpcolor", "findpic")
ALGORITHMS = ("nsf", "bsf", "dsf")


def _copy_to(src: str, dest: Path) -> str:
    """把插件落盘文件另存到 dest;返回绝对路径。"""
    source = Path(src)
    if not source.exists():
        raise CliError(f"插件返回的文件不存在: {src}", EXIT_FAILURE)
    if dest.is_dir():
        dest = dest / source.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    return str(dest.resolve())


# ----------------------------------------------------------------------
# screenshot
# ----------------------------------------------------------------------


def cmd_screenshot(args, app: App) -> int:
    body: dict = {"format": args.img_format, "quality": args.quality}
    module = app.module(args.module)
    if module:
        body["module"] = module
    envelope = app.client.post("/screenshot", body)
    data = require_ok(envelope)
    path = data.get("path")
    if not path:
        raise CliError("插件未返回截图路径", EXIT_FAILURE)
    if args.out:
        saved = _copy_to(path, Path(args.out).expanduser())
        data["savedPath"] = saved
    if output.json_mode():
        output.emit_json(envelope)
        return 0
    output.data(path)
    size = data.get("bytes")
    extra = f"saved={data['savedPath']}" if data.get("savedPath") else ""
    output.data(f"bytes={size} {extra}".rstrip())
    return 0


# ----------------------------------------------------------------------
# nodes / node-params
# ----------------------------------------------------------------------


def build_node_params(args, *, include_defaults: bool) -> dict:
    """构造节点抓取参数(字段与插件「节点设置」一致)。

    include_defaults=True 时(mode/invisible/not-important/algorithm 任意显式给出,
    或 --override)发送完整四个字段;否则返回空 dict 表示沿用插件持久化设置。
    """
    explicit = any(
        value is not None
        for value in (args.mode, args.invisible, args.not_important, args.algorithm)
    )
    if not include_defaults and not explicit:
        return {}
    return {
        "mode": int(args.mode if args.mode is not None else 1),
        "invisible": bool(args.invisible if args.invisible is not None else False),
        "notImportant": bool(args.not_important if args.not_important is not None else True),
        "algorithm": args.algorithm or "nsf",
    }


def _validate_algorithm(args) -> None:
    if args.algorithm is not None and args.algorithm not in ALGORITHMS:
        raise CliError(f"algorithm 只能是 {'/'.join(ALGORITHMS)}", EXIT_USAGE)
    if args.mode is not None and args.mode not in (1, 2):
        raise CliError("mode 只能是 1(增强型)或 2(快速型)", EXIT_USAGE)


def cmd_nodes(args, app: App) -> int:
    _validate_algorithm(args)
    body = build_node_params(args, include_defaults=bool(args.override))
    module = app.module(args.module)
    if module:
        body["module"] = module
    envelope = app.client.post("/nodes", body)
    data = require_ok(envelope)
    xml_path = data.get("xmlPath")
    image_path = data.get("imagePath")
    if not xml_path:
        raise CliError("插件未返回节点 XML 路径", EXIT_FAILURE)

    parsed: list[node_tree.Node] = []
    try:
        parsed = node_tree.parse_nodes_xml(xml_path)
        data["nodes"] = [n.to_dict() for n in parsed]
    except CliError as exc:
        output.warn(f"节点 XML 解析失败,仅返回路径: {exc}")

    if args.dir:
        target = Path(args.dir).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        if image_path:
            data["imageSavedPath"] = _copy_to(image_path, target)
        data["xmlSavedPath"] = _copy_to(xml_path, target)

    if output.json_mode():
        output.emit_json(envelope)
        return 0

    if image_path:
        output.data(image_path)
    output.data(xml_path)
    if data.get("imageSavedPath"):
        output.data(f"imageSaved={data['imageSavedPath']}")
    if data.get("xmlSavedPath"):
        output.data(f"xmlSaved={data['xmlSavedPath']}")
    if not args.no_table and parsed:
        print(node_tree.format_nodes_table(parsed, max_rows=args.max))
    return 0


def cmd_node_params(args, app: App) -> int:
    _validate_algorithm(args)
    body = build_node_params(args, include_defaults=True)
    envelope = app.client.post("/node-params", body)
    require_ok(envelope)
    if output.json_mode():
        output.emit_json(envelope)
    else:
        output.data(
            "已更新节点抓取参数: "
            f"mode={body['mode']} invisible={body['invisible']} "
            f"notImportant={body['notImportant']} algorithm={body['algorithm']}"
        )
    return 0


# ----------------------------------------------------------------------
# ocr
# ----------------------------------------------------------------------


def _parse_ocr_result(result):
    """规范化 /ocr 的 result 字段,兼容插件实际返回的多种形态。

    实测形态:
      - JSON null 或字符串 "null":无识别结果
      - list[dict]:正常识别结果(label/confidence/x/y/width/height)
      - str:设备端信息,也可能是 JSON 串(可解析为 list)
    :return (items, reason):items 为 None 表示无结果;reason 为设备端附加说明(可为空)
    """
    if result is None:
        return None, ""
    if isinstance(result, str):
        text = result.strip()
        if text in ("", "null", "undefined"):
            return None, ""
        try:
            parsed = json.loads(text)
        except ValueError:
            return None, text
        if isinstance(parsed, list):
            return parsed, ""
        if isinstance(parsed, dict):
            return [parsed], ""
        return None, text
    if isinstance(result, list):
        return result, ""
    return [result], ""


def _ocr_log_hint(logs) -> None:
    """无结果时,把设备日志里最相关的一条错误透出,便于定位原因。"""
    if not isinstance(logs, list):
        return
    for entry in logs:
        text = entry.get("text", "") if isinstance(entry, dict) else str(entry)
        if ("OCR失败" in text) or ("JS 执行异常" in text):
            output.data(f"设备日志: {text.strip()}")
            return


def cmd_ocr(args, app: App) -> int:
    if args.type and args.type not in OCR_TYPES:
        raise CliError(f"--type 只能是 {'/'.join(OCR_TYPES)}", EXIT_USAGE)
    body: dict = {"source": "screen"}
    module = app.module(args.module)
    if module:
        body["module"] = module
    if args.type:
        body["type"] = args.type
    envelope = app.client.post("/ocr", body)
    data = require_ok(envelope)
    result = data.get("result")
    if output.json_mode():
        output.emit_json(envelope)
        return 0
    items, reason = _parse_ocr_result(result)
    if items is None:
        output.data("result=null(无识别结果;确认设备/App 已开启 OCR 能力,协议细节见 references/beetap-cli-protocol.md §5.11)")
        if reason:
            output.data(f"设备端信息: {reason}")
        _ocr_log_hint(data.get("logs"))
        return 0
    for item in items:
        if not isinstance(item, dict):
            output.data(f"(非识别项) {item}")
            continue
        label = item.get("label", "")
        confidence = item.get("confidence")
        x, y = item.get("x"), item.get("y")
        width, height = item.get("width"), item.get("height")
        output.data(f"{label}\tconf={confidence}\t({x},{y})\t{width}x{height}")
    output.data(f"count={len(items)}")
    return 0


# ----------------------------------------------------------------------
# test-image
# ----------------------------------------------------------------------


def build_test_image_body(args, module: str | None, *, template: str | None = None) -> dict:
    """构造 /test-image 请求体;template 参数用于覆盖 args.template(已落位的模板路径)。"""
    method = args.method
    if method not in TEST_IMAGE_METHODS:
        raise CliError(f"--method 只能是 {'/'.join(TEST_IMAGE_METHODS)}", EXIT_USAGE)
    body: dict = {"method": method}
    if module:
        body["module"] = module
    if args.threshold is not None:
        body["threshold"] = args.threshold
    region = {"x": args.x, "y": args.y, "ex": args.ex, "ey": args.ey}
    if method == "findcolor":
        if not args.color:
            raise CliError("findcolor 需要 --color 0xRRGGBB-0x偏色", EXIT_USAGE)
        body["color"] = args.color
        body["limit"] = args.limit
        body["orz"] = args.orz
        body.update(region)
    elif method == "findmulticolor":
        if not args.first_color or not args.points:
            raise CliError("findmulticolor 需要 --first-color 与 --points", EXIT_USAGE)
        body["firstColor"] = args.first_color
        body["points"] = args.points
        body.update(region)
    elif method == "cmpcolor":
        if not args.points:
            raise CliError("cmpcolor 需要 --points", EXIT_USAGE)
        body["points"] = args.points
    elif method == "findpic":
        source = template if template is not None else args.template
        if not source:
            raise CliError("findpic 需要 --template <模板图路径>", EXIT_USAGE)
        body["templatePath"] = source
        body.update(region)
        if args.delta_color:
            body["deltaColor"] = args.delta_color
    return body


def _parse_result(raw) -> object:
    """接口的 data.result 是 JSON 字符串,需要二次解析;解析失败原样返回。"""
    if raw is None:
        return None
    if isinstance(raw, (list, dict, bool)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def cmd_test_image(args, app: App) -> int:
    module = app.module(args.module)
    template = args.template
    if args.method == "findpic" and template:
        # 协议 §5.10/§8:findpic 的 templatePath 必须在解析到的工程目录内
        template = ensure_template_in_project(app.client, module, template)
    body = build_test_image_body(args, module, template=template)
    envelope = app.client.post("/test-image", body)
    data = require_ok(envelope)
    parsed = _parse_result(data.get("result"))
    data["resultParsed"] = parsed
    if output.json_mode():
        output.emit_json(envelope)
        return 0
    if parsed is None:
        output.data("result=null(未找到)")
    elif isinstance(parsed, bool):
        output.data(f"result={str(parsed).lower()}")
    elif isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and "x" in item and "y" in item:
                output.data(f"({item['x']},{item['y']})")
            else:
                output.data(json.dumps(item, ensure_ascii=False))
        output.data(f"count={len(parsed)}")
    elif isinstance(parsed, dict) and ("centerX" in parsed or "centerY" in parsed):
        output.data(
            f"center=({parsed.get('centerX')},{parsed.get('centerY')}) "
            f"box=({parsed.get('left')},{parsed.get('top')},{parsed.get('right')},{parsed.get('bottom')}) "
            f"index={parsed.get('index')}"
        )
    else:
        output.data(json.dumps(parsed, ensure_ascii=False))
    duration = data.get("durationMs")
    if duration is not None:
        output.info(f"耗时 {duration} ms")
    return 0

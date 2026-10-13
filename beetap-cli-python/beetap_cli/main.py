"""命令行入口:argparse 命令树 + 分发。

全局参数(-u/--url、-m/--module、--timeout、-f/--format、--env)放在子命令前后均可。
退出码约定见 errors.py(与官方 beetap-android-cli 对齐,智能体以此判断成败)。
"""

from __future__ import annotations

import os
import sys
import argparse

from . import __version__, capture, commands, config, device, doctor, output
from .client import BeeTapClient
from .commands import App
from .errors import CliError, EXIT_USAGE

EPILOG = (
    "示例:\n"
    "  doctor                                  环境检查(Python/配置/插件/工程/设备/能力)\n"
    "  connect --wait 60s                      等待设备连接(先在 IDEA 插件里点「USB 调试」)\n"
    "  run -m lark-tap --wait-timeout 5m -k '登录成功|||登录失败'\n"
    "  run --snippet 'toast(\"hi\"); logd(\"snippet ok\");'\n"
    "  screenshot -o shot.png && nodes --dir evidence\n"
    "  monitor -k '脚本已停止运行' --max-duration 2m\n"
    "\n"
    "设备连接由 IDEA 插件单点管理(协议 v1 / 插件 1.3.10+ 起 CLI /connect 已禁用);\n"
    "更多用法与关键约定见技能目录 SKILL.md / commands.md。"
)


class Parser(argparse.ArgumentParser):
    """参数错误退出码改为 1(与官方 CLI 一致;argparse 默认 2 与等待超时冲突)。"""

    def error(self, message: str):  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"[beetap-cli] 错误: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def _common_args() -> argparse.ArgumentParser:
    """所有子命令共享的全局参数(default=SUPPRESS:未提供时不覆盖根解析器已解析的值)。"""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-u", "--url", metavar="URL", default=argparse.SUPPRESS,
                        help="插件控制端点(默认 http://127.0.0.1:9318,也可用 BEETAP_URL)")
    common.add_argument("-m", "--module", metavar="NAME", default=argparse.SUPPRESS,
                        help="BeeTap 工程目录名/工程名/绝对路径(大小写不敏感;多工程必填,也可用 BEETAP_MODULE)")
    common.add_argument("--timeout", metavar="DUR", type=config.duration_arg,
                        default=argparse.SUPPRESS,
                        help="单次 HTTP 超时,如 30s / 6m(默认 360s;run --wait 请给足)")
    common.add_argument("-f", "--format", dest="format", choices=("text", "json"),
                        default=argparse.SUPPRESS,
                        help="输出格式: text 人类可读(默认) / json 完整信封一行")
    common.add_argument("--env", metavar="PATH", default=argparse.SUPPRESS,
                        help=".env 配置文件路径(默认查找当前目录与技能根目录)")
    return common


# ----------------------------------------------------------------------
# 解析器构造
# ----------------------------------------------------------------------


def build_parser() -> Parser:
    parser = Parser(
        prog="beetap-cli",
        description="遥控 BeeTap IDEA 插件:运行/调试脚本、截图取证、抓节点、图色测试(设备连接在插件 UI 完成)",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[_common_args()],
    )
    parser.add_argument("--version", action="version", version=f"beetap-cli {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<COMMAND>")
    sub.required = True
    common = _common_args()

    _add_doctor(sub, common)
    _add_status_projects(sub, common)
    _add_connect(sub, common)
    _add_run(sub, common)
    _add_signals(sub, common)
    _add_logs(sub, common)
    _add_monitor(sub, common)
    _add_screenshot(sub, common)
    _add_nodes(sub, common)
    _add_node_params(sub, common)
    _add_ocr(sub, common)
    _add_test_image(sub, common)
    _add_raw(sub, common)
    return parser


def _add_doctor(sub, common) -> None:
    p = sub.add_parser("doctor", parents=[common], aliases=["check"],
                       help="环境检查:Python/配置/插件/工程/设备/工程能力")
    p.set_defaults(func=doctor.doctor)


def _add_status_projects(sub, common) -> None:
    p = sub.add_parser("status", parents=[common],
                       help="查看插件版本/端点/设备连接状态/工程列表")
    p.set_defaults(func=commands.cmd_status)

    p = sub.add_parser("projects", parents=[common], help="列出 IDEA 中打开的 BeeTap 工程")
    p.set_defaults(func=commands.cmd_projects)


def _add_connect(sub, common) -> None:
    p = sub.add_parser("connect", parents=[common],
                       help="查看/等待设备连接(连接动作只能在 IDEA 插件里完成)")
    p.add_argument("--wait", metavar="DUR", type=config.duration_arg, default=0.0,
                   help="等待设备连接的最长时间(如 60s;默认只查看当前状态)")
    # 协议 v1(/connect 已禁用)前的旧参数:接受但忽略,避免旧脚本直接报参数错误
    p.add_argument("--mode", default=None, help=argparse.SUPPRESS)
    p.add_argument("--serial", default=None, help=argparse.SUPPRESS)
    p.add_argument("--host", default=None, help=argparse.SUPPRESS)
    p.add_argument("--port", type=int, default=None, help=argparse.SUPPRESS)
    p.set_defaults(func=device.cmd_connect)


def _add_run(sub, common) -> None:
    p = sub.add_parser("run", parents=[common],
                       help="编译并运行工程(默认等待结束并回显日志);或用片段模式只跑一段 JS")
    p.add_argument("--wait", dest="wait", action="store_true", default=True,
                   help="阻塞等待脚本结束/命中关键字/超时(默认)")
    p.add_argument("--no-wait", dest="wait", action="store_false", help="只下发不等待")
    p.add_argument("--wait-timeout", metavar="DUR", type=config.duration_arg, default=300.0,
                   help="等待上限(默认 5m;服务端钳位 [5s,30m],超时返回 stopReason=timeout 且退出码 2)")
    p.add_argument("-k", "--stop-on", metavar="KEYWORD", action="append", default=[],
                   help="停止关键字:'a|||b' 或重复 -k,任一命中(忽略大小写子串)提前返回(退出码 0)")
    p.add_argument("--code", metavar="FILE", default=None,
                   help="运行脚本片段文件(js;'-' 读标准输入),不动工程入口")
    p.add_argument("--snippet", metavar="JS", default=None,
                   help="直接内联一段 JS 片段运行(与 --code 二选一)")
    p.add_argument("--template", metavar="IMG", default=None,
                   help="片段模式随包下发的找图模板图(协议要求位于工程目录内,外部路径自动复制进工程)")
    p.set_defaults(func=device.cmd_run)


def _add_signals(sub, common) -> None:
    for action, label in (("stop", "停止"), ("pause", "暂停"), ("resume", "继续")):
        p = sub.add_parser(action, parents=[common], help=f"{label}设备上正在运行的脚本")
        p.set_defaults(func=device.cmd_signal(action))


def _add_logs(sub, common) -> None:
    p = sub.add_parser("logs", parents=[common],
                       help="读取插件日志缓冲(设备日志/编译输出/插件消息)")
    p.add_argument("--since", type=int, default=0, help="读取该游标之后的日志(配合上次 cursor 增量拉取)")
    p.add_argument("--lines", type=int, default=200, help="最多返回条数(默认 200)")
    p.add_argument("--project", default=None, help="按 IDEA 工程根路径精确过滤(不是 BeeTap 工程目录)")
    p.set_defaults(func=commands.cmd_logs)


def _add_monitor(sub, common) -> None:
    p = sub.add_parser("monitor", parents=[common],
                       help="跟随日志流;-k 命中(忽略大小写)退出 0,超时退出 2(设备端跑脚本时等标记用)")
    p.add_argument("-k", "--stop-on", metavar="KEYWORD", action="append", default=[],
                   help="停止关键字:'a|||b' 或重复 -k;默认「脚本已停止运行」")
    p.add_argument("--max-duration", metavar="DUR", type=config.duration_arg, default=600.0,
                   help="最长跟随时间(默认 10m)")
    p.add_argument("--lines", type=int, default=500, help="每轮最多拉取条数(默认 500)")
    p.add_argument("--initial", action="store_true",
                   help="从缓冲最旧开始(默认只看启动之后的新日志)")
    p.set_defaults(func=commands.cmd_monitor)


def _add_screenshot(sub, common) -> None:
    p = sub.add_parser("screenshot", parents=[common], help="手机截图(插件落盘,返回本机路径)")
    p.add_argument("--img-format", dest="img_format", choices=("png", "jpg"), default="png",
                   help="截图格式(默认 png)")
    p.add_argument("--quality", type=int, default=90, help="jpg 质量 1-100(默认 90)")
    p.add_argument("-o", "--out", metavar="FILE", default=None, help="另存为该路径(目录则保留原文件名)")
    p.set_defaults(func=capture.cmd_screenshot)


def _add_nodes(sub, common) -> None:
    p = sub.add_parser("nodes", parents=[common],
                       help="抓取控件节点树(图+XML),打印紧凑节点表(中心点可直接点击)")
    p.add_argument("--max", type=int, default=120, help="节点表最多显示行数(默认 120)")
    p.add_argument("--no-table", action="store_true", help="只保存文件不渲染节点表")
    p.add_argument("--dir", metavar="DIR", default=None, help="把图+XML 另存到该目录")
    p.add_argument("--override", action="store_true",
                   help="本次抓取应用下面的节点参数(不改插件持久化设置)")
    _add_node_param_flags(p)
    p.set_defaults(func=capture.cmd_nodes)


def _add_node_params(sub, common) -> None:
    p = sub.add_parser("node-params", parents=[common], aliases=["set-node-params"],
                       help="持久化节点抓取参数并同步设备(等同插件「节点设置」)")
    _add_node_param_flags(p)
    p.set_defaults(func=capture.cmd_node_params)


def _add_node_param_flags(p) -> None:
    p.add_argument("--mode", type=int, default=None, choices=(1, 2),
                   help="抓取模式 1=增强型 / 2=快速型(默认 1)")
    p.add_argument("--invisible", dest="invisible", action="store_true", default=None,
                   help="遍历不可见节点")
    p.add_argument("--visible", dest="invisible", action="store_false", default=None,
                   help="不遍历不可见节点(默认)")
    p.add_argument("--not-important", dest="not_important", action="store_true", default=None,
                   help="包含 not-important 节点(默认)")
    p.add_argument("--important", dest="not_important", action="store_false", default=None,
                   help="排除 not-important 节点")
    p.add_argument("--algorithm", choices=("nsf", "bsf", "dsf"), default=None,
                   help="遍历算法(默认 nsf)")


def _add_ocr(sub, common) -> None:
    p = sub.add_parser("ocr", parents=[common], help="对当前屏幕做 OCR(依赖 App 打包能力)")
    p.add_argument("--type", choices=capture.OCR_TYPES, default=None,
                   help="OCR 引擎(缺省用会话默认)")
    p.set_defaults(func=capture.cmd_ocr)


def _add_test_image(sub, common) -> None:
    p = sub.add_parser("test-image", parents=[common],
                       help="手机端图色测试:findcolor / findmulticolor / cmpcolor / findpic")
    p.add_argument("--method", required=True, choices=capture.TEST_IMAGE_METHODS, help="测试方法")
    p.add_argument("--color", default=None, help="findcolor 目标色,如 0xCDD7E9-0x101010")
    p.add_argument("--first-color", dest="first_color", default=None, help="findmulticolor 锚点色")
    p.add_argument("--points", default=None,
                   help='多色条件:findmulticolor "dx|dy|0x色,..." / cmpcolor "x|y|0x色,..."')
    p.add_argument("--template", default=None,
                   help="findpic 模板图路径(协议要求位于工程目录内;外部路径自动复制进工程)")
    p.add_argument("--threshold", type=float, default=None, help="相似度 0-1(默认 0.9)")
    p.add_argument("--delta-color", dest="delta_color", default=None,
                   help="findpic 各通道允许偏差,如 0x101010")
    p.add_argument("--x", type=int, default=0, help="区域起点 x")
    p.add_argument("--y", type=int, default=0, help="区域起点 y")
    p.add_argument("--ex", type=int, default=0, help="区域宽(0=全屏)")
    p.add_argument("--ey", type=int, default=0, help="区域高(0=全屏)")
    p.add_argument("--limit", type=int, default=1, help="findcolor 最多返回个数(默认 1)")
    p.add_argument("--orz", type=int, default=0, help="findcolor 扫描方向 0-4(4=中心向外)")
    p.set_defaults(func=capture.cmd_test_image)


def _add_raw(sub, common) -> None:
    p = sub.add_parser("raw", parents=[common],
                       help="原始端点透传(GET/POST),调试与未来接口兜底")
    p.add_argument("method", help="HTTP 方法: GET / POST")
    p.add_argument("path", help="端点路径,如 /status 或 /run")
    p.add_argument("-b", "--body", default=None, help="JSON 请求体(POST)")
    p.add_argument("--body-file", dest="body_file", default=None, metavar="PATH",
                   help="从文件读取 JSON 请求体('-' 读标准输入)")
    p.set_defaults(func=commands.cmd_raw)


# ----------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    try:
        import signal

        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError, OSError):
        pass

    parser = build_parser()
    args = parser.parse_args(argv)

    # 全局参数用 SUPPRESS 默认值(保证子命令前后均可),未提供时补 None 供命令层直接取用
    for name, default in (("url", None), ("module", None), ("timeout", None),
                          ("format", "text"), ("env", None)):
        if not hasattr(args, name):
            setattr(args, name, default)

    try:
        output.configure(getattr(args, "format", "text") == "json")
        cfg = config.load(
            url=getattr(args, "url", None),
            module=getattr(args, "module", None),
            timeout=getattr(args, "timeout", None),
            env_file=getattr(args, "env", None),
        )
        app = App(cfg, BeeTapClient(cfg.url, cfg.timeout))
        func = getattr(args, "func", None)
        if func is None:
            parser.print_help()
            return EXIT_USAGE
        return int(func(args, app) or 0)
    except CliError as exc:
        output.error(exc.message)
        for line in exc.guidance:
            print(f"[beetap-cli]   {line}", file=sys.stderr)
        return exc.exit_code
    except BrokenPipeError:
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except OSError:
            pass
        return 141
    except KeyboardInterrupt:
        print("[beetap-cli] 已取消", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

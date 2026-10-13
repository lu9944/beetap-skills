"""错误类型与退出码约定(协议 v1 第 4 节)。

退出码与官方 beetap-android-cli 对齐 —— 智能体应以此判断成败,不要解析中文文案:

| 退出码 | 含义 |
|---|---|
| 0 | 成功(含 run 命中关键字、monitor 命中关键字) |
| 1 | 用法/参数错误(含 -m 未找到、工程歧义) |
| 2 | run --wait / monitor 等待超时未命中关键字 |
| 3 | 其它失败(编译失败/截图节点超时/内部错误) |
| 4 | 设备未连接 |
| 5 | 插件不可达(IDEA 没开/端口不对/响应非法,协议里对应客户端本地码 9001) |
| 6 | 已有运行在进行中(busy) |
| 7 | 未识别的响应(未知 code;含 1003 端点被新 IDEA 实例接管) |

接口契约见 references/beetap-cli-protocol.md。
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_TIMEOUT = 2
EXIT_FAILURE = 3
EXIT_NO_DEVICE = 4
EXIT_UNREACHABLE = 5
EXIT_BUSY = 6
EXIT_UNRECOGNIZED = 7

# 插件错误码(code)→ 退出码(见协议 v1 第 4 节)
PLUGIN_ERROR_EXIT = {
    1001: EXIT_USAGE,         # 请求参数错误(/connect 已禁用,恒返此码)
    1002: EXIT_BUSY,          # 已有运行在进行中
    1003: EXIT_UNRECOGNIZED,  # 本实例已被新启动的 IDEA 实例接管(token 不匹配)
    2001: EXIT_NO_DEVICE,     # 设备未连接
    2002: EXIT_FAILURE,       # 编译失败/调试包生成失败
    3001: EXIT_FAILURE,       # 捕获/连接等待超时
    4001: EXIT_USAGE,         # 未找到 BeeTap 工程
    4002: EXIT_USAGE,         # 工程歧义
    5000: EXIT_FAILURE,       # 插件内部错误
}


def plugin_exit(code) -> int:
    """把插件错误码映射为进程退出码;未知 code 按协议归为 7(未识别的响应)。"""
    try:
        value = int(code)
    except (TypeError, ValueError):
        return EXIT_UNRECOGNIZED
    if value == 0:
        return EXIT_OK
    return PLUGIN_ERROR_EXIT.get(value, EXIT_UNRECOGNIZED)


class CliError(Exception):
    """用户可见错误:message 打印到 stderr,进程以 exit_code 退出。"""

    def __init__(
        self,
        message: str,
        exit_code: int = EXIT_FAILURE,
        guidance: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.guidance = list(guidance or [])

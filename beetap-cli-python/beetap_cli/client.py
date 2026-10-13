"""插件 HTTP 客户端(纯标准库 urllib)。

统一处理响应信封 `{code, msg, data}`(见 references/beetap-cli-protocol.md 第 3/4 节):
- 网络不可达 → CliError(退出码 5),附 IDEA/端口排查指引;
- 响应非法(非 JSON / 非 2xx) → 同样视为「插件不可达」(协议客户端本地码 9001 → 退出码 5);
- 插件业务错误码(code != 0)→ CliError(按 errors.PLUGIN_ERROR_EXIT 映射,未知 code → 7);
- 成功 → 返回原始信封,调用方用 `require_ok` 取 data。

端点只监听本机回环,统一绕过 http_proxy 环境变量(默认 opener 会走代理,导致本地端点连不上)。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import __version__
from .errors import (
    CliError,
    EXIT_UNRECOGNIZED,
    EXIT_UNREACHABLE,
    plugin_exit,
)

USER_AGENT = f"beetap-cli/{__version__}"
DEFAULT_TIMEOUT = 360.0

UNREACHABLE_GUIDANCE = [
    "确认 IntelliJ IDEA 已启动,且已打开含 BeeTap 工程的项目(控制端点随插件启动,IDEA 关闭即消失);",
    "确认端点地址:默认 http://127.0.0.1:9318;若启动参数改过 -Dbeetap.cliPort,用 -u/--url 同步;",
    "确认 9318 没被其它进程占用(端口被占用时插件端点启动失败,所有命令表现为不可达);",
    "服务只监听本机回环地址,远程机器上请先做端口转发。",
]

TAKEOVER_GUIDANCE = [
    "端点已被新启动的 IDEA 实例接管(单实例令牌不匹配,code=1003),本实例全部端点拒绝;",
    "确认只有一个 IDEA 实例在服务该端口;",
    "若新实例用 -Dbeetap.cliPort= 指定了其它端口,请用 -u/--url 指向该实例后重试。",
]

# 仅回环端点,绕过代理环境变量
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def require_ok(envelope: dict) -> dict:
    """校验信封 code==0 并返回 data(无 data 或非 dict 时返回 {})。"""
    code = envelope.get("code", 0)
    if code != 0:
        msg = envelope.get("msg") or f"插件返回错误码 {code}"
        if int_or_none(code) == 1003:
            raise CliError(f"插件错误 (code=1003): {msg}", EXIT_UNRECOGNIZED, TAKEOVER_GUIDANCE)
        raise CliError(f"插件错误 (code={code}): {msg}", plugin_exit(code))
    data = envelope.get("data")
    return data if isinstance(data, dict) else {}


class BeeTapClient:
    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(self.base_url)
        if not parsed.scheme or not parsed.hostname:
            raise CliError(f"非法的端点地址: {base_url}", plugin_exit(1001))
        self.timeout = timeout

    # ------------------------------------------------------------------
    # 请求
    # ------------------------------------------------------------------

    def url(self, path: str, params: dict | None = None) -> str:
        full = f"{self.base_url}/{path.lstrip('/')}"
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        if clean:
            full += "?" + urllib.parse.urlencode(clean)
        return full

    def get(self, path: str, params: dict | None = None, timeout: float | None = None) -> dict:
        return self._send("GET", path, params=params, timeout=timeout)

    def post(self, path: str, body: dict | None = None, timeout: float | None = None) -> dict:
        payload = json.dumps(body if body is not None else {}, ensure_ascii=False).encode("utf-8")
        return self._send("POST", path, payload=payload, timeout=timeout)

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        payload: bytes | None = None,
        timeout: float | None = None,
    ) -> dict:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.url(path, params), data=payload, headers=headers, method=method
        )
        try:
            with _OPENER.open(request, timeout=timeout or self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:  # 协议规定恒为 200;非 200 视为异常响应
            raw = exc.read()
            if not raw:
                raise CliError(
                    f"插件返回 HTTP {exc.code} {exc.reason}(协议约定恒为 200,应按不可达排查)",
                    EXIT_UNREACHABLE,
                    UNREACHABLE_GUIDANCE,
                ) from exc
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise CliError(
                f"无法连接 BeeTap 插件控制端点 {self.url(path)}: {reason}",
                EXIT_UNREACHABLE,
                UNREACHABLE_GUIDANCE,
            ) from exc

        try:
            envelope = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError as exc:
            preview = raw[:200].decode("utf-8", errors="replace")
            raise CliError(
                f"插件返回了非 JSON 响应(按不可达处理): {preview}",
                EXIT_UNREACHABLE,
                UNREACHABLE_GUIDANCE,
            ) from exc
        if not isinstance(envelope, dict):
            raise CliError(
                f"插件响应格式异常(按不可达处理): {type(envelope).__name__}",
                EXIT_UNREACHABLE,
                UNREACHABLE_GUIDANCE,
            )
        return envelope

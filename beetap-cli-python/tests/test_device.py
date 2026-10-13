"""连接引导与运行控制测试:请求体构造、钳位、关键字展开、日志识别。"""

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from beetap_cli.commands import App, split_keywords
from beetap_cli.config import Config
from beetap_cli.device import (
    build_run_body,
    clamp_wait_timeout,
    cmd_connect,
    cmd_run,
    cmd_signal,
    find_busy,
    find_js_error,
)
from beetap_cli.errors import CliError, EXIT_NO_DEVICE


class FakeClient:
    """伪插件端点:按顺序弹出 /status 响应,记录 POST 请求。"""

    def __init__(self, statuses=None, post_result=None):
        self.statuses = list(statuses or [])
        self.get_calls = []
        self.post_calls = []
        self.post_result = post_result or {"code": 0, "msg": "ok"}

    def get(self, path, params=None, timeout=None):
        self.get_calls.append((path, params))
        data = self.statuses.pop(0) if self.statuses else {"device": {"connected": False}}
        return {"code": 0, "msg": "ok", "data": data}

    def post(self, path, body=None, timeout=None):
        self.post_calls.append((path, body))
        return self.post_result


class SplitKeywordsTest(unittest.TestCase):
    def test_split_and_dedupe(self):
        self.assertEqual(
            split_keywords(["登录成功|||登录失败", "登录成功", " done "]),
            ["登录成功", "登录失败", "done"],
        )

    def test_empty(self):
        self.assertEqual(split_keywords([]), [])
        self.assertEqual(split_keywords(None), [])


class CmdConnectTest(unittest.TestCase):
    """connect 不再 POST /connect(协议 1.3.10+ 已禁用),只查看/等待 + 指引。"""

    def _args(self, **overrides) -> argparse.Namespace:
        values = dict(wait=0.0, mode=None, serial=None, host=None, port=None)
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_connected_returns_zero_without_post(self):
        client = FakeClient([{"device": {"connected": True, "model": "Pixel 3"}}])
        with mock.patch("beetap_cli.output.data") as data:
            code = cmd_connect(self._args(), App(Config(), client))
        self.assertEqual(code, 0)
        self.assertEqual(client.post_calls, [])
        data.assert_called()

    def test_not_connected_exit_4_with_guidance(self):
        client = FakeClient([{"device": {"connected": False}}])
        with mock.patch("beetap_cli.output.data"):
            with self.assertRaises(CliError) as ctx:
                cmd_connect(self._args(), App(Config(), client))
        self.assertEqual(ctx.exception.exit_code, EXIT_NO_DEVICE)
        self.assertTrue(ctx.exception.guidance)
        self.assertEqual(client.post_calls, [])

    def test_wait_polls_until_connected(self):
        client = FakeClient([
            {"device": {"connected": False}},
            {"device": {"connected": True, "model": "Pixel 3"}},
        ])
        with mock.patch("beetap_cli.device.time.sleep"), \
             mock.patch("beetap_cli.output.info"), \
             mock.patch("beetap_cli.output.data"):
            code = cmd_connect(self._args(wait=60.0), App(Config(), client))
        self.assertEqual(code, 0)
        self.assertEqual(len(client.get_calls), 2)
        self.assertEqual(client.post_calls, [])

    def test_wait_timeout_exit_4(self):
        client = FakeClient([
            {"device": {"connected": False}},
            {"device": {"connected": False}},
        ])
        with mock.patch("beetap_cli.device.time.sleep"), \
             mock.patch("beetap_cli.device.time.monotonic", side_effect=[0.0, 0.0, 100.0]), \
             mock.patch("beetap_cli.output.info"):
            with self.assertRaises(CliError) as ctx:
                cmd_connect(self._args(wait=5.0), App(Config(), client))
        self.assertEqual(ctx.exception.exit_code, EXIT_NO_DEVICE)

    def test_legacy_args_ignored_with_warning(self):
        client = FakeClient([{"device": {"connected": True}}])
        with mock.patch("beetap_cli.output.warn") as warn, \
             mock.patch("beetap_cli.output.data"):
            cmd_connect(self._args(mode="wifi", serial="192.168.1.17:5555"),
                        App(Config(), client))
        warn.assert_called()
        self.assertEqual(client.post_calls, [])


class BuildRunBodyTest(unittest.TestCase):
    def test_project_wait_with_keywords(self):
        body = build_run_body(
            module="lark-tap", wait=True, wait_timeout=300.0,
            keywords=["登录成功"], code=None, snippet=None, template=None,
        )
        self.assertEqual(body, {
            "module": "lark-tap",
            "wait": True,
            "timeoutMs": 300000,
            "keywords": ["登录成功"],
        })

    def test_no_wait(self):
        body = build_run_body(module=None, wait=False, wait_timeout=300.0)
        self.assertEqual(body, {"wait": False})

    def test_snippet_and_template(self):
        body = build_run_body(
            module=None, wait=True, wait_timeout=30.0,
            code=None, snippet='toast("hi");', template="/tmp/tpl.png",
        )
        self.assertEqual(body["code"], 'toast("hi");')
        self.assertEqual(body["templatePath"], "/tmp/tpl.png")

    def test_code_and_snippet_conflict(self):
        with self.assertRaises(CliError):
            build_run_body(module=None, wait=True, wait_timeout=30.0,
                           code="x", snippet="y")

    def test_template_requires_snippet(self):
        with self.assertRaises(CliError):
            build_run_body(module=None, wait=True, wait_timeout=30.0,
                           template="/tmp/tpl.png")


class ClampWaitTimeoutTest(unittest.TestCase):
    """服务端 /run timeoutMs 钳位 [5000, 1800000](协议 §5.7)。"""

    def test_within_range(self):
        self.assertEqual(clamp_wait_timeout(300.0), (300.0, None))

    def test_below_min(self):
        value, note = clamp_wait_timeout(1.0)
        self.assertEqual(value, 5.0)
        self.assertIsNotNone(note)

    def test_above_max(self):
        value, note = clamp_wait_timeout(3600.0)
        self.assertEqual(value, 1800.0)
        self.assertIsNotNone(note)


class CmdRunTemplateTest(unittest.TestCase):
    def test_template_outside_project_is_copied_before_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "lark-tap"
            project.mkdir()
            source = Path(tmp) / "tpl.png"
            source.write_bytes(b"png-bytes")
            client = FakeClient(
                statuses=[{"projects": [{"name": "lark-tap", "path": str(project)}]}],
                post_result={"code": 0, "msg": "ok",
                             "data": {"stopReason": "script_stopped", "logs": []}},
            )
            args = argparse.Namespace(
                code=None, snippet='toast("hi");', stop_on=[], wait=True,
                wait_timeout=30.0, template=str(source), module=None,
            )
            with mock.patch("beetap_cli.output.info"), \
                 mock.patch("beetap_cli.output.data"), \
                 mock.patch("beetap_cli.output.warn"), \
                 mock.patch("beetap_cli.output.emit_log_line"):
                code = cmd_run(args, App(Config(), client))
            self.assertEqual(code, 0)
            path, body = client.post_calls[0]
            self.assertEqual(path, "/run")
            self.assertTrue(body["templatePath"].startswith(str(project)))
            self.assertTrue(Path(body["templatePath"]).exists())


class SignalBodyTest(unittest.TestCase):
    """协议 §5.8:stop 带 module 复位运行会话,pause/resume 忽略参数。"""

    def test_stop_sends_module(self):
        client = FakeClient()
        with mock.patch("beetap_cli.output.data"):
            cmd_signal("stop")(argparse.Namespace(module=None),
                               App(Config(module="lark-tap"), client))
        self.assertEqual(client.post_calls, [("/stop", {"module": "lark-tap"})])

    def test_stop_without_module_sends_empty_body(self):
        client = FakeClient()
        with mock.patch("beetap_cli.output.data"):
            cmd_signal("stop")(argparse.Namespace(module=None), App(Config(), client))
        self.assertEqual(client.post_calls, [("/stop", {})])

    def test_pause_ignores_module(self):
        client = FakeClient()
        with mock.patch("beetap_cli.output.data"):
            cmd_signal("pause")(argparse.Namespace(module=None),
                                App(Config(module="lark-tap"), client))
        self.assertEqual(client.post_calls, [("/pause", {})])


class LogMarkersTest(unittest.TestCase):
    def test_js_error(self):
        logs = [{"text": "[设备日志] JS 执行异常: (js/main.js:1): TypeError"}]
        self.assertIsNotNone(find_js_error(logs))
        self.assertIsNone(find_busy(logs))

    def test_busy(self):
        logs = [{"text": "[远程设备]:BUSY: 已有脚本正在运行，请先停止后再试"}]
        self.assertIsNotNone(find_busy(logs))
        self.assertIsNone(find_js_error(logs))

    def test_clean(self):
        logs = [{"text": "[设备日志] 脚本已停止运行"}]
        self.assertIsNone(find_js_error(logs))
        self.assertIsNone(find_busy(logs))


if __name__ == "__main__":
    unittest.main()

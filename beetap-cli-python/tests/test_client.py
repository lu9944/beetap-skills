"""HTTP 客户端测试:信封校验、错误码映射、URL 构造。"""

import io
import json
import unittest
import urllib.error
from unittest import mock

from beetap_cli.client import BeeTapClient, require_ok
from beetap_cli.errors import (
    CliError,
    EXIT_BUSY,
    EXIT_FAILURE,
    EXIT_NO_DEVICE,
    EXIT_UNREACHABLE,
    EXIT_UNRECOGNIZED,
    EXIT_USAGE,
    plugin_exit,
)


class PluginExitTest(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(plugin_exit(0), 0)
        self.assertEqual(plugin_exit(1001), EXIT_USAGE)
        self.assertEqual(plugin_exit(1002), EXIT_BUSY)
        self.assertEqual(plugin_exit(1003), EXIT_UNRECOGNIZED)
        self.assertEqual(plugin_exit(2001), EXIT_NO_DEVICE)
        self.assertEqual(plugin_exit(2002), EXIT_FAILURE)
        self.assertEqual(plugin_exit(3001), EXIT_FAILURE)
        self.assertEqual(plugin_exit(4001), EXIT_USAGE)
        self.assertEqual(plugin_exit(4002), EXIT_USAGE)
        self.assertEqual(plugin_exit(5000), EXIT_FAILURE)

    def test_unknown_code_maps_to_7(self):
        self.assertEqual(plugin_exit(9999), EXIT_UNRECOGNIZED)
        self.assertEqual(plugin_exit(None), EXIT_UNRECOGNIZED)


class RequireOkTest(unittest.TestCase):
    def test_success_returns_data(self):
        data = require_ok({"code": 0, "msg": "ok", "data": {"x": 1}})
        self.assertEqual(data, {"x": 1})

    def test_success_without_data(self):
        self.assertEqual(require_ok({"code": 0, "msg": "ok"}), {})
        self.assertEqual(require_ok({"code": 0, "data": None}), {})

    def test_error_maps_exit_code(self):
        with self.assertRaises(CliError) as ctx:
            require_ok({"code": 1002, "msg": "已有 CLI 运行在进行中"})
        self.assertEqual(ctx.exception.exit_code, EXIT_BUSY)
        self.assertIn("已有 CLI 运行在进行中", ctx.exception.message)

    def test_error_without_message(self):
        with self.assertRaises(CliError) as ctx:
            require_ok({"code": 2001})
        self.assertEqual(ctx.exception.exit_code, EXIT_NO_DEVICE)

    def test_takeover_1003_exit_7_with_guidance(self):
        with self.assertRaises(CliError) as ctx:
            require_ok({"code": 1003, "msg": "本实例已被新启动的 IDEA 实例接管"})
        self.assertEqual(ctx.exception.exit_code, EXIT_UNRECOGNIZED)
        self.assertTrue(ctx.exception.guidance)


class UrlTest(unittest.TestCase):
    def test_url_with_params(self):
        client = BeeTapClient("http://127.0.0.1:9318/")
        url = client.url("/logs", {"since": 0, "lines": 5, "project": None})
        self.assertEqual(url, "http://127.0.0.1:9318/logs?since=0&lines=5")

    def test_invalid_base_url(self):
        with self.assertRaises(CliError):
            BeeTapClient("127.0.0.1:9318")


class SendTest(unittest.TestCase):
    def _client(self):
        return BeeTapClient("http://127.0.0.1:9318", timeout=1.0)

    def test_unreachable_maps_exit_5(self):
        client = self._client()
        with mock.patch(
            "beetap_cli.client._OPENER.open",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with self.assertRaises(CliError) as ctx:
                client.get("/status")
        self.assertEqual(ctx.exception.exit_code, EXIT_UNREACHABLE)
        self.assertTrue(ctx.exception.guidance)

    def test_http_error_json_envelope_is_parsed(self):
        client = self._client()
        body = json.dumps({"code": 4001, "msg": "未找到 BeeTap 工程"}).encode("utf-8")
        error = urllib.error.HTTPError(
            "http://127.0.0.1:9318/status", 500, "Internal Server Error", {}, io.BytesIO(body)
        )
        with mock.patch("beetap_cli.client._OPENER.open", side_effect=error):
            envelope = client.get("/status")
        self.assertEqual(envelope["code"], 4001)

    def test_http_error_without_body_is_unreachable(self):
        client = self._client()
        error = urllib.error.HTTPError(
            "http://127.0.0.1:9318/status", 502, "Bad Gateway", {}, io.BytesIO(b"")
        )
        with mock.patch("beetap_cli.client._OPENER.open", side_effect=error):
            with self.assertRaises(CliError) as ctx:
                client.get("/status")
        self.assertEqual(ctx.exception.exit_code, EXIT_UNREACHABLE)

    def test_non_json_body_is_unreachable(self):
        client = self._client()
        response = mock.MagicMock()
        response.read.return_value = b"<html>oops</html>"
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with mock.patch("beetap_cli.client._OPENER.open", return_value=response):
            with self.assertRaises(CliError) as ctx:
                client.get("/status")
        self.assertIn("非 JSON", ctx.exception.message)
        self.assertEqual(ctx.exception.exit_code, EXIT_UNREACHABLE)

    def test_post_sends_json_body(self):
        client = self._client()
        response = mock.MagicMock()
        response.read.return_value = json.dumps({"code": 0, "msg": "ok"}).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with mock.patch("beetap_cli.client._OPENER.open", return_value=response) as opened:
            envelope = client.post("/run", {"wait": False, "module": "lark-tap"})
        self.assertEqual(envelope["code"], 0)
        request = opened.call_args[0][0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"wait": False, "module": "lark-tap"},
        )


if __name__ == "__main__":
    unittest.main()

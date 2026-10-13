"""取证命令测试:图色请求体、节点参数、result 二次解析。"""

import argparse
import unittest

from beetap_cli.capture import (
    _parse_result,
    build_node_params,
    build_test_image_body,
)
from beetap_cli.errors import CliError


def _test_image_args(**overrides) -> argparse.Namespace:
    values = dict(
        method="findcolor",
        color="0x000000-0x101010",
        first_color=None,
        points=None,
        template=None,
        threshold=0.9,
        delta_color=None,
        x=0, y=0, ex=0, ey=0,
        limit=3, orz=0,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def _node_args(**overrides) -> argparse.Namespace:
    values = dict(mode=None, invisible=None, not_important=None, algorithm=None)
    values.update(overrides)
    return argparse.Namespace(**values)


class TestImageBodyTest(unittest.TestCase):
    def test_findcolor(self):
        body = build_test_image_body(_test_image_args(), "lark-tap")
        self.assertEqual(body["method"], "findcolor")
        self.assertEqual(body["color"], "0x000000-0x101010")
        self.assertEqual(body["limit"], 3)
        self.assertEqual(body["module"], "lark-tap")
        self.assertEqual(body["threshold"], 0.9)

    def test_findcolor_requires_color(self):
        with self.assertRaises(CliError):
            build_test_image_body(_test_image_args(color=None), None)

    def test_findmulticolor(self):
        body = build_test_image_body(
            _test_image_args(method="findmulticolor", color=None,
                             first_color="0xFFFFFF", points="10|0|0x000000"),
            None,
        )
        self.assertEqual(body["firstColor"], "0xFFFFFF")
        self.assertEqual(body["points"], "10|0|0x000000")

    def test_cmpcolor(self):
        body = build_test_image_body(
            _test_image_args(method="cmpcolor", color=None, points="100|200|0xFF0000"),
            None,
        )
        self.assertEqual(body, {"method": "cmpcolor", "threshold": 0.9, "points": "100|200|0xFF0000"})

    def test_findpic(self):
        body = build_test_image_body(
            _test_image_args(method="findpic", color=None, template="/tmp/tpl.png",
                             delta_color="0x101010"),
            None,
        )
        self.assertEqual(body["templatePath"], "/tmp/tpl.png")
        self.assertEqual(body["deltaColor"], "0x101010")

    def test_findpic_template_override(self):
        """落位后的模板路径(工程目录内)覆盖命令行原始路径。"""
        body = build_test_image_body(
            _test_image_args(method="findpic", color=None, template="/tmp/orig.png"),
            None,
            template="/proj/bt_work_temp/android/beetap_cli_template.png",
        )
        self.assertEqual(
            body["templatePath"], "/proj/bt_work_temp/android/beetap_cli_template.png"
        )

    def test_findpic_requires_template(self):
        with self.assertRaises(CliError):
            build_test_image_body(_test_image_args(method="findpic", color=None), None)

    def test_bad_method(self):
        with self.assertRaises(CliError):
            build_test_image_body(_test_image_args(method="findcircle"), None)


class ParseResultTest(unittest.TestCase):
    def test_json_string(self):
        self.assertEqual(_parse_result('[{"x":1,"y":2}]'), [{"x": 1, "y": 2}])
        self.assertIsNone(_parse_result("null"))
        self.assertEqual(_parse_result("true"), True)

    def test_native_values(self):
        self.assertEqual(_parse_result(None), None)
        self.assertEqual(_parse_result([1, 2]), [1, 2])

    def test_unparseable(self):
        self.assertEqual(_parse_result("not-json"), "not-json")


class NodeParamsTest(unittest.TestCase):
    def test_defaults_when_nothing_given(self):
        self.assertEqual(build_node_params(_node_args(), include_defaults=False), {})

    def test_defaults_when_any_flag_given(self):
        body = build_node_params(_node_args(mode=2), include_defaults=False)
        self.assertEqual(body, {"mode": 2, "invisible": False, "notImportant": True, "algorithm": "nsf"})

    def test_include_defaults(self):
        body = build_node_params(_node_args(), include_defaults=True)
        self.assertEqual(body, {"mode": 1, "invisible": False, "notImportant": True, "algorithm": "nsf"})

    def test_explicit_values(self):
        body = build_node_params(
            _node_args(invisible=True, not_important=False, algorithm="bsf"),
            include_defaults=True,
        )
        self.assertEqual(body["invisible"], True)
        self.assertEqual(body["notImportant"], False)
        self.assertEqual(body["algorithm"], "bsf")


if __name__ == "__main__":
    unittest.main()

"""工程解析与模板落位测试(协议 v1 §5.7 / §5.10 / §8)。

协议要求 /run(templatePath)与 /test-image findpic 的模板必须位于
解析到的 BeeTap 工程目录内(越界 1001);本 CLI 对工程外模板自动复制进
`<工程>/bt_work_temp/android/beetap_cli_template.<ext>`。
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from beetap_cli.errors import CliError
from beetap_cli.project import ensure_template_in_project, pick_project_path


class PickProjectPathTest(unittest.TestCase):
    PROJECTS = [
        {"name": "demo", "projectName": "DemoApp", "path": "/work/demo"},
        {"name": "other", "projectName": "Other", "path": "/work/other"},
    ]

    def test_by_name_case_insensitive(self):
        self.assertEqual(pick_project_path(self.PROJECTS, "DEMO"), "/work/demo")

    def test_by_project_name(self):
        self.assertEqual(pick_project_path(self.PROJECTS, "demoapp"), "/work/demo")

    def test_by_absolute_path(self):
        self.assertEqual(pick_project_path(self.PROJECTS, "/work/other"), "/work/other")

    def test_module_trailing_slash(self):
        self.assertEqual(pick_project_path(self.PROJECTS, "demo/"), "/work/demo")

    def test_no_module_requires_single(self):
        self.assertIsNone(pick_project_path(self.PROJECTS, None))
        self.assertEqual(pick_project_path(self.PROJECTS[:1], None), "/work/demo")

    def test_not_found(self):
        self.assertIsNone(pick_project_path(self.PROJECTS, "nope"))


class FakeClient:
    def __init__(self, data):
        self.data = data
        self.get_calls = []

    def get(self, path, params=None, timeout=None):
        self.get_calls.append((path, params))
        return {"code": 0, "msg": "ok", "data": self.data}


class EnsureTemplateTest(unittest.TestCase):
    def test_inside_project_used_as_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "demo"
            project.mkdir()
            tpl = project / "tpl.png"
            tpl.write_bytes(b"x")
            client = FakeClient({"projects": [{"name": "demo", "path": str(project)}]})
            with mock.patch("beetap_cli.output.info") as info:
                result = ensure_template_in_project(client, "demo", str(tpl))
            self.assertEqual(result, str(tpl))
            info.assert_not_called()

    def test_outside_project_copied_into_bt_work_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "demo"
            project.mkdir()
            tpl = Path(tmp) / "patch.png"
            tpl.write_bytes(b"png-bytes")
            client = FakeClient({"projects": [{"name": "demo", "path": str(project)}]})
            with mock.patch("beetap_cli.output.info"):
                result = ensure_template_in_project(client, "demo", str(tpl))
            target = Path(result)
            self.assertEqual(target.name, "beetap_cli_template.png")
            self.assertEqual(target.parent, project / "bt_work_temp" / "android")
            self.assertEqual(target.read_bytes(), b"png-bytes")

    def test_unresolvable_project_passes_through_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            tpl = Path(tmp) / "patch.png"
            tpl.write_bytes(b"x")
            client = FakeClient({"projects": []})
            with mock.patch("beetap_cli.output.warn") as warn:
                result = ensure_template_in_project(client, None, str(tpl))
            self.assertEqual(result, str(tpl))
            warn.assert_called()

    def test_missing_template_raises(self):
        client = FakeClient({"projects": []})
        with self.assertRaises(CliError):
            ensure_template_in_project(client, None, "/no/such/file.png")


if __name__ == "__main__":
    unittest.main()

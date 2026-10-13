"""节点 XML 解析与表格渲染测试。"""

import tempfile
import unittest
from pathlib import Path

from beetap_cli import nodes as node_tree

XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" desc="" clz="VRoot" bounds="[0,0][0,0]" clickable="false"/>
  <node index="0" text="登录" desc="login button" resource-id="com.demo:id/btn_login"
        clz="android.widget.Button" pkg="com.demo" bounds="[100,200][300,260]"
        clickable="true" long-clickable="false" scrollable="false" enabled="true"/>
  <node index="1" text="" desc="" id="list" class="android.widget.ListView"
        bounds="[0,300][1080,2000]" scrollable="true" clickable="false"/>
  <node index="2" text="搜索" desc="" resource-id="com.demo:id/输入框"
        clz="android.widget.EditText" bounds="[0,100][1080,180]" editable="true" focused="true"/>
</hierarchy>
"""


class ParseNodesTest(unittest.TestCase):
    def _parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nodes.xml"
            path.write_text(XML, encoding="utf-8")
            return node_tree.parse_nodes_xml(path)

    def test_parse_all_nodes(self):
        parsed = self._parse()
        self.assertEqual(len(parsed), 4)

    def test_center_and_flags(self):
        parsed = self._parse()
        button = parsed[1]
        self.assertEqual(button.text, "登录")
        self.assertEqual(button.desc, "login button")
        self.assertEqual(button.resource_id, "com.demo:id/btn_login")
        self.assertEqual(button.short_id, "btn_login")
        self.assertEqual(button.center, (200, 230))
        self.assertEqual(button.flags, "C")

    def test_scrollable_and_editable_flags(self):
        parsed = self._parse()
        self.assertEqual(parsed[2].flags, "S")
        self.assertEqual(parsed[3].flags, "EF")

    def test_to_dict_roundtrip(self):
        parsed = self._parse()
        payload = parsed[1].to_dict()
        self.assertEqual(payload["center"], [200, 230])
        self.assertTrue(payload["clickable"])

    def test_interesting_filter(self):
        parsed = self._parse()
        # 第一个 VRoot 无文本/描述/交互,不进表格
        self.assertFalse(parsed[0].is_interesting())
        self.assertTrue(parsed[1].is_interesting())


class RenderTableTest(unittest.TestCase):
    def _parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nodes.xml"
            path.write_text(XML, encoding="utf-8")
            return node_tree.parse_nodes_xml(path)

    def test_table_contains_rows_and_center(self):
        table = node_tree.format_nodes_table(self._parse())
        self.assertIn("登录", table)
        self.assertIn("(200,230)", table)
        self.assertIn("btn_login", table)
        self.assertIn("显示", table)

    def test_max_rows(self):
        table = node_tree.format_nodes_table(self._parse(), max_rows=1)
        self.assertIn("其余", table)


if __name__ == "__main__":
    unittest.main()

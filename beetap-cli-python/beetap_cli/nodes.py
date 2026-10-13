"""控件节点树解析与紧凑表格渲染。

插件 /nodes 落盘的 XML 每个 <node> 带 text/desc/clz/resource-id/bounds 等属性;
本模块把 XML 解析为 Node 列表,并渲染官方 CLI 风格的紧凑节点表
(text / desc / id / class / 中心点 / flags),供智能体选择点击目标。
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .errors import CliError, EXIT_FAILURE

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def _bool(attrs: dict, *names: str) -> bool:
    for name in names:
        value = attrs.get(name)
        if value is not None:
            return value == "true"
    return False


def _first(attrs: dict, *names: str) -> str:
    for name in names:
        value = attrs.get(name)
        if value is not None:
            return value
    return ""


@dataclass
class Node:
    text: str = ""
    desc: str = ""
    resource_id: str = ""
    clz: str = ""
    package: str = ""
    bounds: tuple[int, int, int, int] | None = None
    clickable: bool = False
    long_clickable: bool = False
    scrollable: bool = False
    editable: bool = False
    focused: bool = False
    checked: bool = False
    checkable: bool = False
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def center(self) -> tuple[int, int] | None:
        if not self.bounds:
            return None
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def flags(self) -> str:
        marks = []
        if self.clickable:
            marks.append("C")
        if self.long_clickable:
            marks.append("L")
        if self.scrollable:
            marks.append("S")
        if self.editable:
            marks.append("E")
        if self.focused:
            marks.append("F")
        if self.checkable:
            marks.append("K")
        return "".join(marks) or "-"

    @property
    def short_id(self) -> str:
        return self.resource_id.rsplit("/", 1)[-1] if self.resource_id else ""

    def is_interesting(self) -> bool:
        """有信息量(可点击/可滚动/可编辑/有文本描述)的节点才进表格。"""
        return bool(
            self.text
            or self.desc
            or self.resource_id
            or self.clickable
            or self.long_clickable
            or self.scrollable
            or self.editable
            or self.checkable
        )

    def to_dict(self) -> dict:
        center = self.center
        return {
            "text": self.text,
            "desc": self.desc,
            "resourceId": self.resource_id,
            "clz": self.clz,
            "package": self.package,
            "bounds": list(self.bounds) if self.bounds else None,
            "center": list(center) if center else None,
            "flags": self.flags,
            "clickable": self.clickable,
            "longClickable": self.long_clickable,
            "scrollable": self.scrollable,
            "editable": self.editable,
            "focused": self.focused,
            "checked": self.checked,
            "checkable": self.checkable,
        }


def parse_node_element(element: ET.Element) -> Node:
    attrs = element.attrib
    bounds = None
    match = _BOUNDS_RE.match(attrs.get("bounds", ""))
    if match:
        x1, y1, x2, y2 = (int(g) for g in match.groups())
        bounds = (x1, y1, x2, y2)
    return Node(
        text=_first(attrs, "text"),
        desc=_first(attrs, "desc", "content-desc"),
        resource_id=_first(attrs, "resource-id", "id"),
        clz=_first(attrs, "clz", "class"),
        package=_first(attrs, "pkg", "package"),
        bounds=bounds,
        clickable=_bool(attrs, "clickable"),
        long_clickable=_bool(attrs, "long-clickable", "longClickable"),
        scrollable=_bool(attrs, "scrollable"),
        editable=_bool(attrs, "editable"),
        focused=_bool(attrs, "focused"),
        checked=_bool(attrs, "checked"),
        checkable=_bool(attrs, "checkable"),
        raw={k: v for k, v in attrs.items()},
    )


def parse_nodes_xml(path: str | Path) -> list[Node]:
    """解析节点 XML,返回全部 <node>(含无语义节点;渲染时再过滤)。"""
    path = Path(path)
    if not path.exists():
        raise CliError(f"节点 XML 不存在: {path}", EXIT_FAILURE)
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise CliError(f"解析节点 XML 失败: {path}: {exc}", EXIT_FAILURE) from exc
    return [parse_node_element(element) for element in tree.iter("node")]


# ----------------------------------------------------------------------
# 紧凑表格渲染(中文按宽度对齐)
# ----------------------------------------------------------------------


def _char_width(char: str) -> int:
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def _width(text: str) -> int:
    return sum(_char_width(ch) for ch in text)


def _clip(text: str, width: int) -> str:
    if _width(text) <= width:
        return text
    out = []
    used = 0
    for char in text:
        w = _char_width(char)
        if used + w > width - 1:
            break
        out.append(char)
        used += w
    return "".join(out) + "…"


def _pad(text: str, width: int) -> str:
    text = _clip(text, width)
    return text + " " * max(0, width - _width(text))


_COLUMNS = [
    ("#", 4),
    ("text", 30),
    ("desc", 18),
    ("id", 22),
    ("class", 26),
    ("center", 12),
    ("flags", 5),
]


def format_nodes_table(
    nodes: list[Node],
    max_rows: int = 120,
    include_trivial: bool = False,
) -> str:
    """渲染紧凑节点表;默认只显示有信息量的节点,最多 max_rows 行。"""
    selected = [n for n in nodes if include_trivial or n.is_interesting()]
    shown = selected[:max_rows]
    header = " ".join(_pad(title, width) for title, width in _COLUMNS).rstrip()
    lines = [header, "-" * min(_width(header), 120)]
    for index, node in enumerate(shown, start=1):
        center = node.center
        center_text = f"({center[0]},{center[1]})" if center else "-"
        clz = node.clz.rsplit(".", 1)[-1] if node.clz else "-"
        row = [
            str(index),
            node.text or "-",
            node.desc or "-",
            node.short_id or "-",
            clz or "-",
            center_text,
            node.flags,
        ]
        lines.append(" ".join(_pad(value, width) for value, (_, width) in zip(row, _COLUMNS)).rstrip())
    if len(selected) > len(shown):
        lines.append(f"... 其余 {len(selected) - len(shown)} 个节点未显示(用 --max 调整)")
    lines.append(f"合计: {len(nodes)} 个节点, 显示 {len(shown)} 个(有信息量 {len(selected)} 个)")
    return "\n".join(lines)

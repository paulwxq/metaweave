"""元数据注释的共享规范化工具。"""

from __future__ import annotations

from typing import Any


def normalize_comment(value: Any) -> str:
    """将注释规范化为去除首尾空白的字符串。

    ``None``、非字符串以及仅含空白字符的值都按缺失注释处理。
    """

    if not isinstance(value, str):
        return ""
    return value.strip()

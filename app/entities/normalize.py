"""实体字段的归一化辅助。

数据库里的 JSON 列可以存成 NULL，Qdrant payload 也可能缺字段或存成标量，
直接 `for x in value` 会抛 TypeError，或者更糟：把字符串按字符拆开迭代。
"""

from typing import Any


def as_list(value: Any) -> list:
    """把任意值归一化成一个列表。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]

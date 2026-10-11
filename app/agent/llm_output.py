"""大模型 JSON 输出的结构校验。

召回 / 过滤这几个节点都依赖“模型只输出 JSON 数组或对象”，但
`JsonOutputParser` 只保证能解析成 JSON，**不保证形状**：

- `recall_*` 里 `keywords + result`，模型若返回 dict 就会 TypeError；
- `filter_table` 里 `table_info["name"] in result`，模型若返回数组就恒为 False，
  于是过滤出 0 张表，下游拿着一份空 schema 去生成 SQL —— **不报错，但结果是错的**。

所以这里统一做严格校验：形状不对就抛 :class:`LLMOutputError`，
宁可让这一次查询明确失败，也不要悄悄给出错误答案。
"""

from typing import Any

import re


class LLMOutputError(ValueError):
    """模型返回的结构不符合预期。"""


_SQL_FENCE = re.compile(
    r"^(?:```|~~~)[A-Za-z0-9_-]*[ \t]*\n(?P<body>.*?)(?:\n[ \t]*(?:```|~~~)[ \t]*)?$",
    re.S,
)


def strip_sql_code_fence(text: str) -> str:
    """去掉模型给 SQL 加的 markdown 代码围栏。

    提示词里要求「只输出 SQL」，但模型有时仍会写成 `` ```sql ... ``` ``，
    甚至只写单行反引号。不剥掉的话护栏会因为首字符是反引号而判定「不是 SELECT/WITH」，
    白白消耗一次校正机会（每次校正都是一次模型调用）。
    """
    if not isinstance(text, str):
        return text

    stripped = text.strip()
    fenced = _SQL_FENCE.match(stripped)
    if fenced:
        return fenced.group("body").strip()

    # 单行 `select ...` 这种写法
    if len(stripped) >= 2 and stripped.startswith("`") and stripped.endswith("`"):
        return stripped.strip("`").strip()

    return stripped


_KEY_CANDIDATES = ("keywords", "items", "result", "values", "data")


def as_string_list(value: Any, *, field: str = "关键词") -> list[str]:
    """把模型输出归一化成字符串列表。

    容忍“被包了一层对象”的写法（如 ``{"keywords": [...]}``），
    也容忍单个字符串；其余情况一律报错。
    """
    if isinstance(value, dict):
        for key in (field, *_KEY_CANDIDATES):
            if key in value:
                return as_string_list(value[key], field=field)
        if len(value) == 1:
            return as_string_list(next(iter(value.values())), field=field)
        raise LLMOutputError(f"模型返回的{field}应为 JSON 数组，实际是对象：{_brief(value)}")

    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []

    if not isinstance(value, (list, tuple)):
        raise LLMOutputError(f"模型返回的{field}应为 JSON 数组，实际是：{_brief(value)}")

    items: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                items.append(text)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            items.append(str(item))
        else:
            raise LLMOutputError(f"{field}列表里出现了非字符串元素：{_brief(item)}")
    return items


def as_table_columns_map(value: Any) -> dict[str, list[str]]:
    """校验并归一化 ``{表名: [字段名, ...]}``。"""
    if not isinstance(value, dict):
        raise LLMOutputError(f"模型返回的表字段结构应为 JSON 对象，实际是：{_brief(value)}")

    result: dict[str, list[str]] = {}
    for table_name, columns in value.items():
        if not isinstance(table_name, str) or not table_name.strip():
            raise LLMOutputError(f"表名不合法：{_brief(table_name)}")
        result[table_name.strip()] = as_string_list(columns, field=f"表 {table_name} 的字段")
    return result


def _brief(value: Any, limit: int = 120) -> str:
    text = repr(value)
    return text if len(text) <= limit else f"{text[:limit]}..."

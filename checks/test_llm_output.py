"""模型输出结构校验（app/agent/llm_output.py）。

这里防的是「静默给错结果」：形状不对时旧代码会算出空集并继续往下走，
最典型的是 filter_table 过滤出 0 张表、下游拿着空 schema 编造 SQL。
另外还负责剥掉模型给 SQL 加的 markdown 围栏 —— 不剥掉会被护栏当成
「不是 SELECT/WITH」直接拒绝，白白浪费一次校正机会。
"""

import pytest

from app.agent.llm_output import (
    LLMOutputError,
    as_string_list,
    as_table_columns_map,
    strip_sql_code_fence,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("select 1", "select 1"),
        ("  select 1  ", "select 1"),
        ("```sql\nselect 1\n```", "select 1"),
        ("```\nselect 1\n```", "select 1"),
        ("~~~sql\nselect 1\n~~~", "select 1"),
        ("```sql\nselect 1", "select 1"),  # 模型输出被截断、围栏没闭合
        ("`select 1`", "select 1"),  # 单行反引号
        ("select 1;\n", "select 1;"),  # 结尾分号交给护栏处理，这里不越权
    ],
)
def test_strip_sql_code_fence(value, expected):
    assert strip_sql_code_fence(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (["a", "b"], ["a", "b"]),
        ({"keywords": ["a"]}, ["a"]),
        ({"items": ["a", "b"]}, ["a", "b"]),
        ({"whatever": ["a"]}, ["a"]),  # 单键对象也认
        ("单条", ["单条"]),
        ([], []),
        ([" a ", "", "  "], ["a"]),
        ([1, 2], ["1", "2"]),
        ("   ", []),
    ],
)
def test_as_string_list_normalizes(value, expected):
    assert as_string_list(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        {"a": 1, "b": 2},  # 多键对象无法归因
        123,
        None,
        [["x"]],  # 嵌套数组
        [None],
        [True],
    ],
)
def test_as_string_list_rejects_bad_shapes(value):
    with pytest.raises(LLMOutputError):
        as_string_list(value)


def test_as_table_columns_map_normalizes():
    assert as_table_columns_map({"dim_region": ["province"], " fact_order ": ["order_amount"]}) == {
        "dim_region": ["province"],
        "fact_order": ["order_amount"],
    }


def test_as_table_columns_map_accepts_single_column_as_string():
    assert as_table_columns_map({"t": "order_amount"}) == {"t": ["order_amount"]}


def test_as_table_columns_map_empty_is_allowed():
    assert as_table_columns_map({}) == {}


@pytest.mark.parametrize(
    "value",
    [
        ["dim_region"],  # 模型返回数组而不是对象
        {"": ["a"]},  # 表名为空
        {"t": [[]]},  # 字段是嵌套数组
    ],
)
def test_as_table_columns_map_rejects_bad_shapes(value):
    with pytest.raises(LLMOutputError):
        as_table_columns_map(value)

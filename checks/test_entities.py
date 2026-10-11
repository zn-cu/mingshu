"""实体字段归一化（app/entities）。

数据库里的 JSON 列可以为 NULL，Qdrant payload 也可能缺字段或存成标量；
不归一化的话下游 `for x in value` 会抛 TypeError，或者更糟——把字符串按字符迭代。
"""

from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.normalize import as_list


def make_column(**overrides) -> ColumnInfo:
    payload = dict(
        id="t.c", name="c", type="int", role="measure",
        examples=["x"], description="d", alias=["y"], table_id="t",
    )
    payload.update(overrides)
    return ColumnInfo(**payload)


def test_none_becomes_empty_list():
    column = make_column(examples=None, alias=None)
    assert column.examples == []
    assert column.alias == []


def test_scalar_is_wrapped():
    assert make_column(examples="单值").examples == ["单值"]


def test_tuple_is_converted():
    assert make_column(alias=("a", "b")).alias == ["a", "b"]


def test_existing_list_is_kept():
    column = make_column(examples=["x"], alias=["y"])
    assert column.examples == ["x"]
    assert column.alias == ["y"]


def test_metric_info_normalizes():
    metric = MetricInfo(id="GMV", name="GMV", description="d", relevant_columns=None, alias=None)
    assert metric.relevant_columns == []
    assert metric.alias == []


def test_examples_can_be_appended_after_normalization():
    """merge_retrieved_info 会往 examples 里追加召回到的取值。"""
    column = make_column(examples=None)
    column.examples.append("华北")
    assert column.examples == ["华北"]


def test_as_list_is_idempotent():
    assert as_list(as_list("a")) == ["a"]
    assert as_list([]) == []

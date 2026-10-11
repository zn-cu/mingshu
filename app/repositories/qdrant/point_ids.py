"""向量点 id 的确定性生成。

一个字段/指标会写入多个向量点（名称、描述、每个别名各一个），
用短文本分别做语义匹配能明显提高召回率 —— 这是有意的设计。

但点 id 必须**由内容派生**：旧实现用 `uuid.uuid4()`，每次重建元知识都会新增一批点，
重复执行只会让集合越来越大、召回里全是重复项。这里改成 UUIDv5，
同样的内容永远得到同样的 id，重复构建是覆盖（upsert）而不是追加。
"""

from __future__ import annotations

import uuid

# 固定命名空间：UUIDv5 的哈希空间，保证跨进程、跨机器结果一致
_NAMESPACE = uuid.UUID("1f2b7a9c-6d4e-5f31-9c8a-2b7d4e6f1a03")


def build_point_id(owner_id: str, kind: str) -> str:
    """生成确定性点 id。

    :param owner_id: 字段/指标的业务 id，如 ``fact_order.order_amount``
    :param kind: 区分同一 owner 的多个向量点，如 ``name`` / ``description`` / ``alias:销售额``
    """
    return str(uuid.uuid5(_NAMESPACE, f"{owner_id}|{kind}"))

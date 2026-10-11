"""向量点 id 与向量点构造（元知识幂等构建的关键）。

旧实现用 uuid4 生成点 id，每重建一次就多一批点；这里确保 id 由内容派生。
"""

import uuid

from app.repositories.qdrant.point_ids import build_point_id
from app.services.meta_knowledge_service import MetaKnowledgeService


def test_same_content_same_id():
    assert build_point_id("fact_order.order_amount", "name") == build_point_id("fact_order.order_amount", "name")


def test_different_kind_different_id():
    assert build_point_id("fact_order.order_amount", "name") != build_point_id("fact_order.order_amount", "description")


def test_different_owner_different_id():
    assert build_point_id("fact_order.order_amount", "name") != build_point_id("fact_order.order_quantity", "name")


def test_id_is_valid_uuid():
    uuid.UUID(build_point_id("fact_order.order_amount", "name"))


def test_ids_are_unique_per_text_variant():
    texts = ["名称", "描述", "别名1", "别名2"]
    ids = {build_point_id("t.c", kind) for kind in texts}
    assert len(ids) == len(texts)


def test_build_points_skips_blank_texts():
    points = MetaKnowledgeService._build_points(
        owner_id="t.c", name="字段名", description="", alias=["", "   "], payload={}
    )
    assert [point["embedding_text"] for point in points] == ["字段名"]


def test_build_points_deduplicates_texts():
    points = MetaKnowledgeService._build_points(
        owner_id="t.c", name="字段名", description="别名A", alias=["别名A", "字段名", "别名B"], payload={}
    )
    assert sorted(point["embedding_text"] for point in points) == sorted(["字段名", "别名A", "别名B"])


def test_build_points_keeps_payload_and_deterministic_ids():
    payload = {"id": "t.c", "name": "c"}
    first = MetaKnowledgeService._build_points(
        owner_id="t.c", name="字段名", description="描述", alias=["别名"], payload=payload
    )
    second = MetaKnowledgeService._build_points(
        owner_id="t.c", name="字段名", description="描述", alias=["别名"], payload=payload
    )
    assert [point["id"] for point in first] == [point["id"] for point in second]
    assert all(point["payload"] == payload for point in first)


def test_build_points_returns_empty_when_everything_blank():
    assert MetaKnowledgeService._build_points(owner_id="t.c", name="", description=None, alias=[], payload={}) == []

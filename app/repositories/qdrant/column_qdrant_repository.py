from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchAny,
    PointStruct,
    VectorParams,
)

from app.conf.app_config import app_config
from app.entities.column_info import ColumnInfo


class ColumnQdrantRepository:
    collection_name = "column_info_collection"

    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def ensure_collection(self):
        if not await self.client.collection_exists(self.collection_name):
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=app_config.qdrant.embedding_size, distance=Distance.COSINE)
            )

    async def delete_by_column_ids(self, column_ids: list[str]) -> None:
        """按 payload 中的字段 id 删除向量点。

        重建元知识前先清理：否则配置里删掉的别名会留下孤立向量点，
        一直参与召回（点 id 由内容派生，不删就只会被覆盖，不会自动消失）。
        """
        if not column_ids:
            return
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="id", match=MatchAny(any=list(column_ids)))])
            ),
            wait=True,
        )

    async def upsert(self, ids: list[str], embeddings: list[list[float]], payloads: list[dict], batch_size: int = 10):
        points: list[PointStruct] = [PointStruct(id=id, vector=embedding, payload=payload) for id, embedding, payload in
                                     zip(ids, embeddings, payloads)]
        for i in range(0, len(points), batch_size):
            # wait=True：等写入确认，避免失败被静默吞掉
            await self.client.upsert(collection_name=self.collection_name, points=points[i:i + batch_size], wait=True)

    async def search(self, embedding: list[float], score_threshold: float = 0.6, limit: int = 20) -> list[ColumnInfo]:
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            limit=limit,
            score_threshold=score_threshold
        )
        return [ColumnInfo(**point.payload) for point in result.points]

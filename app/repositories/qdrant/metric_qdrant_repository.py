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
from app.entities.metric_info import MetricInfo


class MetricQdrantRepository:
    collection_name = "metric_info_collection"

    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def ensure_collection(self):
        if not await self.client.collection_exists(self.collection_name):
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=app_config.qdrant.embedding_size, distance=Distance.COSINE)
            )

    async def delete_by_metric_ids(self, metric_ids: list[str]) -> None:
        """按 payload 中的指标 id 删除向量点，保证重建是覆盖而不是追加。"""
        if not metric_ids:
            return
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(must=[FieldCondition(key="id", match=MatchAny(any=list(metric_ids)))])
            ),
            wait=True,
        )

    async def upsert(self, ids: list[str], embeddings: list[list[float]], payloads: list[dict], batch_size: int = 10):
        points: list[PointStruct] = [PointStruct(id=id, vector=embedding, payload=payload) for id, embedding, payload in
                                     zip(ids, embeddings, payloads)]
        for i in range(0, len(points), batch_size):
            await self.client.upsert(collection_name=self.collection_name, points=points[i:i + batch_size], wait=True)

    async def search(self, embedding: list[float], score_threshold: float = 0.6, limit: int = 20) -> list[MetricInfo]:
        result = await self.client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            limit=limit,
            score_threshold=score_threshold
        )
        return [MetricInfo(**point.payload) for point in result.points]

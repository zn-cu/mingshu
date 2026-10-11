from dataclasses import asdict

from elasticsearch import AsyncElasticsearch

from app.conf.app_config import app_config
from app.entities.value_info import ValueInfo


class ValueESRepository:
    index_mappings = {
        "dynamic": False,
        "properties": {
            "id": {"type": "keyword"},
            "value": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_max_word"},
            "column_id": {"type": "keyword"}
        }
    }

    def __init__(self, client: AsyncElasticsearch):
        self.client = client

    @property
    def index_name(self) -> str:
        """索引名以配置为准。

        原来这里硬编码 "value_index"，而配置里的 es.index_name 从未被任何代码使用 ——
        两者不一致，会让自检、运维排查时找错对象（启动自检就曾据此误报「索引不存在」）。
        """
        return app_config.es.index_name

    async def ensure_index(self):
        if not await self.client.indices.exists(index=self.index_name):
            await self.client.indices.create(
                index=self.index_name,
                mappings=self.index_mappings
            )

    async def delete_by_column_ids(self, column_ids: list[str]) -> int:
        """删除这些字段下的所有取值文档。

        旧实现用 ES 自动生成的文档 id，重复构建会不断产生重复文档；
        重建前按 column_id 清一遍，既保证幂等，也能清掉配置里不再同步的取值。
        """
        if not column_ids:
            return 0
        resp = await self.client.delete_by_query(
            index=self.index_name,
            query={"terms": {"column_id": list(column_ids)}},
            refresh=True,
            conflicts="proceed",
        )
        return int(resp.get("deleted", 0))

    async def index(self, value_infos: list[ValueInfo], batch_size: int = 20) -> int:
        """批量写入，文档 _id 固定用 ValueInfo.id（幂等：重跑覆盖同一文档）。"""
        indexed = 0
        for i in range(0, len(value_infos), batch_size):
            batch_value_infos = value_infos[i:i + batch_size]
            batch_operations = []
            for value_info in batch_value_infos:
                batch_operations.append(
                    {
                        "index": {
                            "_index": self.index_name,
                            "_id": value_info.id,
                        }
                    }
                )
                batch_operations.append(asdict(value_info))
            resp = await self.client.bulk(operations=batch_operations)
            if resp.get("errors"):
                failures = [
                    item["index"]
                    for item in resp.get("items", [])
                    if item.get("index", {}).get("error")
                ]
                raise RuntimeError(f"ES 批量写入存在失败文档（{len(failures)} 条）：{failures[:3]}")
            indexed += len(batch_value_infos)

        # 统一刷新一次，保证构建结束后立刻可查
        await self.client.indices.refresh(index=self.index_name)
        return indexed

    async def search(self, keyword: str, score_threshold: float = 0.6, limit: int = 20) -> list[ValueInfo]:
        resp = await self.client.search(
            index=self.index_name,
            query={
                "match": {
                    "value": keyword
                }
            },
            size=limit,
            min_score=score_threshold
        )
        return [ValueInfo(**hit['_source']) for hit in resp['hits']['hits']]

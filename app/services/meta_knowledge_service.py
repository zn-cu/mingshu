from dataclasses import asdict
from pathlib import Path

from langchain_openai import OpenAIEmbeddings
from omegaconf import OmegaConf

from app.conf.meta_config import MetaConfig
from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.entities.value_info import ValueInfo
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.repositories.qdrant.point_ids import build_point_id
from app.core.log import logger

# 向量化批大小
EMBEDDING_BATCH_SIZE = 20
# 维度取值分批拉取的页大小与总量上限
VALUE_FETCH_BATCH_SIZE = 5000
VALUE_TOTAL_LIMIT = 100000


class MetaKnowledgeService:
    def __init__(self,
                 meta_mysql_repository: MetaMySQLRepository,
                 dw_mysql_repository: DWMySQLRepository,
                 column_qdrant_repository: ColumnQdrantRepository,
                 embedding_client: OpenAIEmbeddings,
                 value_es_repository: ValueESRepository,
                 metric_qdrant_repository: MetricQdrantRepository):
        self.meta_mysql_repository: MetaMySQLRepository = meta_mysql_repository
        self.dw_mysql_repository: DWMySQLRepository = dw_mysql_repository
        self.column_qdrant_repository: ColumnQdrantRepository = column_qdrant_repository
        self.embedding_client: OpenAIEmbeddings = embedding_client
        self.value_es_repository: ValueESRepository = value_es_repository
        self.metric_qdrant_repository: MetricQdrantRepository = metric_qdrant_repository

    # ------------------------------------------------------------ 通用工具 --

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """分批向量化。"""
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[i:i + EMBEDDING_BATCH_SIZE]
            batch_embeddings = await self.embedding_client.aembed_documents(batch)
            if len(batch_embeddings) != len(batch):
                # 数量和顺序必须与入参一致，否则向量会和 payload 错位
                raise RuntimeError(
                    f"向量服务返回数量与请求不一致：请求 {len(batch)} 条，返回 {len(batch_embeddings)} 条"
                )
            embeddings.extend(batch_embeddings)
        return embeddings

    @staticmethod
    def _build_points(owner_id: str, name: str | None, description: str | None,
                      alias: list[str], payload: dict) -> list[dict]:
        """一个字段/指标生成多个向量点：名称、描述、每个别名各一个。

        这是有意的设计——用短文本分别做语义匹配，召回率明显好于把整段拼成一个向量。
        点 id 由内容派生（见 point_ids.build_point_id），所以重复构建是覆盖而非追加；
        同一 owner 内文本为空或重复的会直接跳过，避免写入无意义的向量。
        """
        points: list[dict] = []
        seen: set[str] = set()

        candidates: list[tuple[str, str | None]] = [("name", name), ("description", description)]
        candidates.extend((f"alias:{alias_text}", alias_text) for alias_text in alias)

        for kind, text in candidates:
            text = (text or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            points.append({
                "id": build_point_id(owner_id, kind),
                "embedding_text": text,
                "payload": payload,
            })
        return points

    async def _collect_column_values(self, table_name: str, column_name: str,
                                     total_limit: int = VALUE_TOTAL_LIMIT) -> list:
        """分批取字段去重取值。

        旧实现是一条 `select distinct ... limit 100000` 把结果一次性拉进内存；
        这里按页拉取，每页最多 VALUE_FETCH_BATCH_SIZE 行。
        （用 OFFSET 翻页，表极大时页数变多会变慢；当前维度字段规模很小，够用。）
        """
        values: list = []
        offset = 0
        while len(values) < total_limit:
            batch_limit = min(VALUE_FETCH_BATCH_SIZE, total_limit - len(values))
            page = await self.dw_mysql_repository.get_column_values(
                table_name, column_name, limit=batch_limit, offset=offset
            )
            if not page:
                break
            values.extend(page)
            offset += len(page)
            if len(page) < batch_limit:
                break
        if len(values) >= total_limit:
            logger.warning(f"{table_name}.{column_name} 的取值达到上限 {total_limit}，可能还有未同步的取值")
        return values

    # ---------------------------------------------------------------- 表 --

    async def _save_tables_to_meta_db(self, meta_config: MetaConfig) -> list[ColumnInfo]:
        table_infos: list[TableInfo] = []
        column_infos: list[ColumnInfo] = []

        for table in meta_config.tables:
            # table -> table_info
            table_info = TableInfo(id=table.name,
                                   name=table.name,
                                   role=table.role,
                                   description=table.description)
            table_infos.append(table_info)

            # 查询字段类型
            column_types = await self.dw_mysql_repository.get_column_types(table.name)

            for column in table.columns:
                # 查询字段取值示例
                column_values = await self.dw_mysql_repository.get_column_values(table.name, column.name)
                # column -> column_info
                column_info = ColumnInfo(id=f"{table.name}.{column.name}",
                                         name=column.name,
                                         type=column_types[column.name],
                                         role=column.role,
                                         examples=column_values,
                                         description=column.description,
                                         alias=column.alias,
                                         table_id=table.name)
                column_infos.append(column_info)

        table_ids = [table_info.id for table_info in table_infos]
        # 先删后插且在同一事务内：重复执行不会撞主键，也不会留下配置里已删除的表/字段
        async with self.meta_mysql_repository.session.begin():
            await self.meta_mysql_repository.delete_tables_and_columns(table_ids)
            self.meta_mysql_repository.save_table_infos(table_infos)
            self.meta_mysql_repository.save_column_infos(column_infos)

        logger.info(f"元数据库已重建：{len(table_infos)} 张表、{len(column_infos)} 个字段")
        return column_infos

    async def _save_columns_to_qdrant(self, column_infos: list[ColumnInfo]):
        await self.column_qdrant_repository.ensure_collection()

        points: list[dict] = []
        for column_info in column_infos:
            points.extend(self._build_points(
                owner_id=column_info.id,
                name=column_info.name,
                description=column_info.description,
                alias=column_info.alias,
                payload=asdict(column_info),
            ))

        # 先按字段 id 清理旧向量点，再写入（点 id 由内容派生，删掉配置里去掉的别名才不会被遗留）
        await self.column_qdrant_repository.delete_by_column_ids([column_info.id for column_info in column_infos])

        embeddings = await self._embed_texts([point["embedding_text"] for point in points])
        await self.column_qdrant_repository.upsert(
            ids=[point["id"] for point in points],
            embeddings=embeddings,
            payloads=[point["payload"] for point in points],
        )
        logger.info(f"字段向量已重建：{len(column_infos)} 个字段 -> {len(points)} 个向量点")

    async def _save_values_to_es(self, meta_config: MetaConfig):
        await self.value_es_repository.ensure_index()

        sync_columns = [
            f"{table.name}.{column.name}"
            for table in meta_config.tables
            for column in table.columns
            if column.sync
        ]

        value_infos: list[ValueInfo] = []
        for column_id in sync_columns:
            table_name, column_name = column_id.split(".", 1)
            current_column_values = await self._collect_column_values(table_name, column_name)
            value_infos.extend(
                ValueInfo(id=f"{column_id}.{value}", value=value, column_id=column_id)
                for value in current_column_values
            )

        deleted = await self.value_es_repository.delete_by_column_ids(sync_columns)
        indexed = await self.value_es_repository.index(value_infos)
        logger.info(
            f"取值全文索引已重建：清理 {deleted} 条旧文档，写入 {indexed} 条（{len(sync_columns)} 个字段）"
        )

    # -------------------------------------------------------------- 指标 --

    async def _save_metrics_to_meta_db(self, meta_config: MetaConfig) -> list[MetricInfo]:
        metric_infos: list[MetricInfo] = []
        column_metrics: list[ColumnMetric] = []

        for metric in meta_config.metrics:
            # metric->MetricInfo
            metric_info = MetricInfo(
                id=metric.name,
                name=metric.name,
                description=metric.description,
                relevant_columns=metric.relevant_columns,
                alias=metric.alias
            )
            metric_infos.append(metric_info)
            for column in metric.relevant_columns:
                # column -> ColumnMetric
                column_metric = ColumnMetric(
                    column_id=column,
                    metric_id=metric.name
                )
                column_metrics.append(column_metric)

        metric_ids = [metric_info.id for metric_info in metric_infos]
        async with self.meta_mysql_repository.session.begin():
            await self.meta_mysql_repository.delete_metrics(metric_ids)
            self.meta_mysql_repository.save_metric_infos(metric_infos)
            self.meta_mysql_repository.save_column_metrics(column_metrics)

        logger.info(f"元数据库指标已重建：{len(metric_infos)} 个指标、{len(column_metrics)} 条关联")
        return metric_infos

    async def _save_metrics_to_qdrant(self, metric_infos: list[MetricInfo]):
        await self.metric_qdrant_repository.ensure_collection()

        points: list[dict] = []
        for metric_info in metric_infos:
            points.extend(self._build_points(
                owner_id=metric_info.id,
                name=metric_info.name,
                description=metric_info.description,
                alias=metric_info.alias,
                payload=asdict(metric_info),
            ))

        await self.metric_qdrant_repository.delete_by_metric_ids([metric_info.id for metric_info in metric_infos])

        embeddings = await self._embed_texts([point["embedding_text"] for point in points])
        await self.metric_qdrant_repository.upsert(
            ids=[point["id"] for point in points],
            embeddings=embeddings,
            payloads=[point["payload"] for point in points],
        )
        logger.info(f"指标向量已重建：{len(metric_infos)} 个指标 -> {len(points)} 个向量点")

    # ---------------------------------------------------------------- 入口 --

    async def build(self, config_path: Path):
        # 1. 读取配置文件
        context = OmegaConf.load(config_path)
        schema = OmegaConf.structured(MetaConfig)
        meta_config: MetaConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))
        logger.info("加载配置文件成功")

        # 2. 根据配置文件同步指定的表信息
        if meta_config.tables:
            # 2.1 将表信息和字段信息保存meta数据库中
            column_infos = await self._save_tables_to_meta_db(meta_config)
            logger.info("保存表信息和字段信息到数据库成功")

            # 2.2 对字段信息建立向量索引
            await self._save_columns_to_qdrant(column_infos)
            logger.info("为字段信息建立向量索引成功")

            # 2.3 对指定的维度字段取值建立全文索引
            await self._save_values_to_es(meta_config)
            logger.info("为指定的维度字段取值建立全文索引成功")

        # 3. 根据配置文件同步指定的指标信息
        if meta_config.metrics:
            # 3.1 将指标信息保存meta数据库中
            metric_infos = await self._save_metrics_to_meta_db(meta_config)
            logger.info("保存指标信息到数据库成功")

            # 3.2 对指标信息建立向量索引
            await self._save_metrics_to_qdrant(metric_infos)
            logger.info("为指标信息建立向量索引成功")

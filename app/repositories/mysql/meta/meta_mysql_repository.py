from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.column_info import ColumnInfo
from app.entities.column_metric import ColumnMetric
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.models.column_info import ColumnInfoMySQL
from app.models.column_metric import ColumnMetricMySQL
from app.models.metric_info import MetricInfoMySQL
from app.models.table_info import TableInfoMySQL
from app.repositories.mysql.meta.mappers.column_info_mapper import ColumnInfoMapper
from app.repositories.mysql.meta.mappers.column_metric_mapper import ColumnMetricMapper
from app.repositories.mysql.meta.mappers.metric_info_mapper import MetricInfoMapper
from app.repositories.mysql.meta.mappers.table_info_mapper import TableInfoMapper


class MetaMySQLRepository:
    """元数据库访问。

    写入侧是「先删后插」配套使用：元知识构建脚本在一个事务里先删掉本次同步范围内的旧记录，
    再插入新记录，因此重复执行不会撞主键、也不会留下配置里已删除的表/字段。
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ 写入
    def save_table_infos(self, table_infos: list[TableInfo]):
        self.session.add_all([TableInfoMapper.to_model(table_info) for table_info in table_infos])

    def save_column_infos(self, column_infos: list[ColumnInfo]):
        self.session.add_all([ColumnInfoMapper.to_model(column_info) for column_info in column_infos])

    def save_metric_infos(self, metric_infos: list[MetricInfo]):
        self.session.add_all([MetricInfoMapper.to_model(metric_info) for metric_info in metric_infos])

    def save_column_metrics(self, column_metrics: list[ColumnMetric]):
        self.session.add_all([ColumnMetricMapper.to_model(column_metric) for column_metric in column_metrics])

    # ------------------------------------------------------------ 重建前清理
    async def delete_tables_and_columns(self, table_ids: list[str]) -> None:
        """删除这些表及其字段记录（字段先删，避免留下孤儿字段）。"""
        if not table_ids:
            return
        await self.session.execute(
            delete(ColumnInfoMySQL).where(ColumnInfoMySQL.table_id.in_(table_ids))
        )
        await self.session.execute(
            delete(TableInfoMySQL).where(TableInfoMySQL.id.in_(table_ids))
        )

    async def delete_metrics(self, metric_ids: list[str]) -> None:
        """删除这些指标及其字段关联。"""
        if not metric_ids:
            return
        await self.session.execute(
            delete(ColumnMetricMySQL).where(ColumnMetricMySQL.metric_id.in_(metric_ids))
        )
        await self.session.execute(
            delete(MetricInfoMySQL).where(MetricInfoMySQL.id.in_(metric_ids))
        )

    # ---------------------------------------------------------------- 批量读
    async def get_column_infos_by_ids(self, ids: list[str]) -> dict[str, ColumnInfo]:
        """一次取回多个字段，避免逐个查询（原来每个字段一次往返）。"""
        if not ids:
            return {}
        result = await self.session.execute(
            select(ColumnInfoMySQL).where(ColumnInfoMySQL.id.in_(ids))
        )
        return {
            column_info_mysql.id: ColumnInfoMapper.to_entity(column_info_mysql)
            for column_info_mysql in result.scalars().all()
        }

    async def get_table_infos_by_ids(self, ids: list[str]) -> dict[str, TableInfo]:
        if not ids:
            return {}
        result = await self.session.execute(
            select(TableInfoMySQL).where(TableInfoMySQL.id.in_(ids))
        )
        return {
            table_info_mysql.id: TableInfoMapper.to_entity(table_info_mysql)
            for table_info_mysql in result.scalars().all()
        }

    async def get_key_columns_by_table_ids(self, table_ids: list[str]) -> dict[str, list[ColumnInfo]]:
        """一次取回多张表的主外键字段（原来每张表一次查询）。"""
        if not table_ids:
            return {}
        result = await self.session.execute(
            select(ColumnInfoMySQL)
            .where(ColumnInfoMySQL.table_id.in_(table_ids))
            .where(ColumnInfoMySQL.role.in_(("primary_key", "foreign_key")))
        )
        grouped: dict[str, list[ColumnInfo]] = {}
        for column_info_mysql in result.scalars().all():
            grouped.setdefault(column_info_mysql.table_id, []).append(
                ColumnInfoMapper.to_entity(column_info_mysql)
            )
        return grouped

from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.state import AgentState, TableInfoState, MetricInfoState, ColumnInfoState
from app.agent.step import step
from app.core.log import logger
from app.entities.column_info import ColumnInfo
from app.entities.metric_info import MetricInfo
from app.entities.table_info import TableInfo
from app.entities.value_info import ValueInfo


@step("合并召回信息")
async def merge_retrieved_info(state: AgentState, runtime: Runtime[AgentContext]):
    """把三路召回结果合并成下游生成 SQL 需要的表/字段结构。

    元数据库查询全部走批量：原来是「每个字段一次、每张表两次」的 N+1，
    一次问答要几十次往返；现在固定 2~3 次（补字段、补主外键、取表信息）。
    """
    retrieved_column_infos: list[ColumnInfo] = state["retrieved_column_infos"]
    retrieved_metric_infos: list[MetricInfo] = state["retrieved_metric_infos"]
    retrieved_value_infos: list[ValueInfo] = state["retrieved_value_infos"]

    meta_mysql_repository = runtime.context["meta_mysql_repository"]

    column_infos_map: dict[str, ColumnInfo] = {
        column_info.id: column_info for column_info in retrieved_column_infos
    }

    # 1) 一次性补齐元数据库里有、但召回结果里没有的字段（指标关联字段、取值所属字段）
    needed_column_ids: list[str] = []
    for metric_info in retrieved_metric_infos:
        needed_column_ids.extend(metric_info.relevant_columns)
    needed_column_ids.extend(value_info.column_id for value_info in retrieved_value_infos)

    missing_column_ids = list(dict.fromkeys(
        column_id for column_id in needed_column_ids if column_id not in column_infos_map
    ))
    if missing_column_ids:
        found_column_infos = await meta_mysql_repository.get_column_infos_by_ids(missing_column_ids)
        for column_id in missing_column_ids:
            column_info = found_column_infos.get(column_id)
            if column_info is None:
                logger.warning(f"字段 {column_id} 在元数据中不存在，已跳过")
                continue
            column_infos_map[column_id] = column_info

    # 2) 把召回字段取值补进字段示例（上面已告警过的缺失字段这里不再重复刷屏）
    for value_info in retrieved_value_infos:
        column_info = column_infos_map.get(value_info.column_id)
        if column_info is None:
            continue
        if value_info.value not in column_info.examples:
            column_info.examples.append(value_info.value)

    table_to_columns_map: dict[str, list[ColumnInfo]] = {}
    for column_info in column_infos_map.values():
        table_to_columns_map.setdefault(column_info.table_id, []).append(column_info)

    # 3) 一次性补齐所有表的主外键字段
    table_ids = list(table_to_columns_map.keys())
    key_columns_map = await meta_mysql_repository.get_key_columns_by_table_ids(table_ids)
    for table_id, column_infos in table_to_columns_map.items():
        existing_column_ids = {column_info.id for column_info in column_infos}
        for key_column in key_columns_map.get(table_id, []):
            if key_column.id not in existing_column_ids:
                column_infos.append(key_column)
                existing_column_ids.add(key_column.id)

    # 4) 一次性取回所有表信息
    table_infos_map = await meta_mysql_repository.get_table_infos_by_ids(table_ids)

    table_infos: list[TableInfoState] = []
    for table_id, column_infos in table_to_columns_map.items():
        table_info: TableInfo | None = table_infos_map.get(table_id)
        if table_info is None:
            logger.warning(f"字段所属的表 {table_id} 在元数据中不存在，已跳过该表")
            continue
        columns = [
            ColumnInfoState(
                name=column_info.name,
                type=column_info.type,
                role=column_info.role,
                examples=column_info.examples,
                description=column_info.description,
                alias=column_info.alias,
            )
            for column_info in column_infos
        ]
        table_infos.append(TableInfoState(
            name=table_info.name,
            role=table_info.role,
            description=table_info.description,
            columns=columns,
        ))

    metric_infos: list[MetricInfoState] = [
        MetricInfoState(
            name=metric_info.name,
            description=metric_info.description,
            relevant_columns=metric_info.relevant_columns,
            alias=metric_info.alias,
        )
        for metric_info in retrieved_metric_infos
    ]

    return {
        "table_infos": table_infos,
        "metric_infos": metric_infos,
    }

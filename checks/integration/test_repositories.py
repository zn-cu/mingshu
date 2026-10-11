"""需要真实依赖的集成检查（MySQL / Qdrant / ES / 向量服务）。

默认跳过，本地起好 docker 后这样跑：

    $env:DA_RUN_INTEGRATION = '1'; uv run pytest checks/integration -v

这里只做**只读**验证：不写数据、不建表，避免污染环境。
数据库层面的「写操作被拒」由只读账号保证（见 README 的「注意事项」）。
"""

import os

import pytest

from app.conf.app_config import app_config

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        os.environ.get("DA_RUN_INTEGRATION") != "1",
        reason="需要真实依赖；设置 DA_RUN_INTEGRATION=1 后运行",
    ),
]


@pytest.fixture
async def dw_repository():
    from app.clients.mysql_client_manager import dw_mysql_client_manager
    from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository

    dw_mysql_client_manager.init()
    try:
        async with dw_mysql_client_manager.session_factory() as session:
            yield DWMySQLRepository(session)
    finally:
        await dw_mysql_client_manager.close()


@pytest.fixture
async def meta_repository():
    from app.clients.mysql_client_manager import meta_mysql_client_manager
    from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository

    meta_mysql_client_manager.init()
    try:
        async with meta_mysql_client_manager.session_factory() as session:
            yield MetaMySQLRepository(session)
    finally:
        await meta_mysql_client_manager.close()


async def test_select_works(dw_repository):
    result = await dw_repository.run("select count(*) as cnt from fact_order")
    assert len(result.rows) == 1
    assert result.rows[0]["cnt"] > 0


async def test_row_limit_truncates_and_flags(dw_repository, monkeypatch):
    monkeypatch.setattr(app_config.query, "row_limit", 3)
    result = await dw_repository.run("select * from fact_order")
    assert len(result.rows) == 3
    assert result.truncated is True
    assert result.row_limit == 3


async def test_query_own_limit_smaller_than_cap_is_respected(dw_repository, monkeypatch):
    monkeypatch.setattr(app_config.query, "row_limit", 50)
    result = await dw_repository.run("select * from fact_order limit 2")
    assert len(result.rows) == 2
    assert result.truncated is False


async def test_order_by_is_preserved_when_appending_limit(dw_repository, monkeypatch):
    monkeypatch.setattr(app_config.query, "row_limit", 1000)
    result = await dw_repository.run("select order_id from fact_order order by order_id desc")
    ids = [row["order_id"] for row in result.rows]
    assert ids == sorted(ids, reverse=True)


async def test_cte_query_works(dw_repository):
    result = await dw_repository.run("with t as (select 1 as a union all select 2) select * from t")
    assert len(result.rows) == 2


async def test_validate_accepts_cte_and_reports_bad_sql(dw_repository):
    from sqlalchemy.exc import SQLAlchemyError

    from app.core.db_errors import is_infrastructure_error, mysql_errno

    await dw_repository.validate("with t as (select 1 as a) select * from t")

    with pytest.raises(SQLAlchemyError) as excinfo:
        await dw_repository.validate("select nonexistent_column_xyz from fact_order")
    # 关键回归：未知字段必须被归为「SQL 问题」，否则不会走校正流程
    assert mysql_errno(excinfo.value) == 1054
    assert is_infrastructure_error(excinfo.value) is False


async def test_guard_blocks_write_statements(dw_repository):
    from app.core.sql_guard import UnsafeSQLError

    with pytest.raises(UnsafeSQLError):
        await dw_repository.run("delete from fact_order")
    with pytest.raises(UnsafeSQLError):
        await dw_repository.run("select 1; drop table fact_order")


async def test_meta_batch_queries(meta_repository):
    columns = await meta_repository.get_column_infos_by_ids(
        ["fact_order.order_id", "fact_order.order_amount", "不存在的字段"]
    )
    assert set(columns) == {"fact_order.order_id", "fact_order.order_amount"}

    tables = await meta_repository.get_table_infos_by_ids(["fact_order", "dim_region"])
    assert set(tables) == {"fact_order", "dim_region"}

    key_columns = await meta_repository.get_key_columns_by_table_ids(["fact_order"])
    assert key_columns["fact_order"]
    assert all(column.role in ("primary_key", "foreign_key") for column in key_columns["fact_order"])


async def test_meta_batch_queries_short_circuit_on_empty_input(meta_repository):
    assert await meta_repository.get_column_infos_by_ids([]) == {}
    assert await meta_repository.get_table_infos_by_ids([]) == {}
    assert await meta_repository.get_key_columns_by_table_ids([]) == {}

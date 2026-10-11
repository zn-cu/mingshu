from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.conf.app_config import app_config
from app.core.log import logger
from app.core.sql_guard import (
    apply_row_limit,
    assert_read_only,
    assert_safe_identifier,
)


@dataclass(slots=True)
class QueryResult:
    """一次查询的结果，附带“是否被行数上限截断”的标记。"""

    rows: list[dict]
    truncated: bool = False
    row_limit: int | None = None


class DWMySQLRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_column_types(self, table_name: str) -> dict[str, str]:
        table = assert_safe_identifier(table_name, what="表名")
        result = await self.session.execute(text(f"show columns from {table}"))
        # [{Field:order_id,Type:varchar(30),Null:No},{Field:customer_id,Type:varchar(20),Null:YES}]
        return {row["Field"]: row["Type"] for row in result.mappings().fetchall()}

    async def get_column_values(self, table_name: str, column_name: str, limit: int = 10,
                                offset: int = 0) -> list[Any]:
        """取字段的去重取值。

        offset 用于分批拉取：维度字段取值可能很多，一次性 `limit 100000` 会把结果全拉进内存。
        """
        table = assert_safe_identifier(table_name, what="表名")
        column = assert_safe_identifier(column_name, what="字段名")
        sql = f"select distinct {column} from {table} limit {int(limit)} offset {int(offset)}"
        result = await self.session.execute(text(sql))
        return [row[0] for row in result.fetchall()]

    async def get_db_info(self) -> dict[str, str]:
        result = await self.session.execute(text("select version()"))
        version = result.scalar()
        dialect = self.session.bind.dialect.name
        return {"dialect": dialect, "version": version}

    async def validate(self, sql: str) -> str:
        """校验 SQL 是否可执行，返回通过校验（去掉结尾分号）后的语句。

        先用安全护栏挡住非只读语句，再用 EXPLAIN 检查语法与对象是否存在。
        两种情况都抛异常，由上层决定是否走“校正 SQL”分支。
        """
        checked = assert_read_only(sql)
        await self.session.execute(text(f"explain {checked}"))
        return checked

    async def run(self, sql: str) -> QueryResult:
        """执行只读查询。

        三道限制：合规校验（只读 + 单语句）、SQL 执行时间上限、返回行数上限。
        """
        checked = assert_read_only(sql)

        row_limit = int(app_config.query.row_limit)
        limited_sql = apply_row_limit(checked, row_limit)

        await self._apply_statement_timeout()

        result = await self.session.execute(text(limited_sql))
        rows = [dict(row) for row in result.mappings().fetchall()]

        truncated = row_limit > 0 and len(rows) > row_limit
        if truncated:
            rows = rows[:row_limit]
            logger.warning(f"查询结果超过上限 {row_limit} 行，已截断")

        return QueryResult(rows=rows, truncated=truncated, row_limit=row_limit or None)

    async def _apply_statement_timeout(self) -> None:
        """限制单条 SQL 的执行时间（只对只读 SELECT 生效）。

        SET SESSION 会留在连接池的这个连接上，但每次查询都重设，幂等且开销极小。
        """
        timeout_ms = int(app_config.query.sql_timeout_ms)
        if timeout_ms <= 0:
            return
        await self.session.execute(text(f"SET SESSION max_execution_time = {timeout_ms}"))

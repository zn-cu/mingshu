from langgraph.runtime import Runtime
from sqlalchemy.exc import SQLAlchemyError

from app.agent.context import AgentContext
from app.agent.state import AgentState
from app.agent.step import step
from app.conf.app_config import app_config
from app.core.db_errors import error_summary, is_infrastructure_error, mysql_errno
from app.core.log import logger
from app.core.sql_guard import UnsafeSQLError
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository


class SQLCorrectionExhausted(RuntimeError):
    """SQL 反复校验不过，且自动校正次数已用完。"""


@step("校验SQL")
async def validate_sql(state: AgentState, runtime: Runtime[AgentContext]):
    sql = state["sql"]
    dw_mysql_repository: DWMySQLRepository = runtime.context["dw_mysql_repository"]

    try:
        checked_sql = await dw_mysql_repository.validate(sql)
    except UnsafeSQLError as e:
        # 不安全的语句 → 交给 correct_sql 去改，这一步本身算“校验完成”
        return _retry_or_fail(state, f"未通过安全校验：{e}")
    except SQLAlchemyError as e:
        if is_infrastructure_error(e):
            # 数据库不可用/超时：不是 SQL 的错，触发校正只会浪费模型调用
            logger.exception(f"校验SQL 失败（数据库不可用，errno={mysql_errno(e)}）: {e}")
            raise
        return _retry_or_fail(state, f"EXPLAIN 未通过（errno={mysql_errno(e)}）：{error_summary(e)}")

    logger.info("SQL 校验通过")
    # 把通过校验（去掉结尾分号）的语句写回 state，保证真正执行的就是校验过的那条
    return {"error": None, "sql": checked_sql}


def _retry_or_fail(state: AgentState, message: str) -> dict:
    """校验失败后决定：还有校正余额就返回错误让图去校正，用完则明确失败。

    次数用完后**必须报错终止**，不能把一条已知校验不过的 SQL 放过去执行 ——
    原来的图是 correct_sql → run_sql，校正结果不再校验就直接执行了。
    """
    used = int(state.get("sql_correction_count", 0))
    budget = int(app_config.agent.max_sql_corrections)

    if used >= budget:
        raise SQLCorrectionExhausted(
            f"SQL 校验未通过，已自动校正 {used} 次仍未成功。最后一次的错误：{message}"
        )

    logger.info(f"SQL 校验未通过，进入第 {used + 1}/{budget} 次自动校正：{message}")
    return {"error": message}

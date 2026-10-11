from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.state import AgentState
from app.agent.step import step
from app.core.log import logger


@step("运行SQL")
async def run_sql(state: AgentState, runtime: Runtime[AgentContext]):
    sql = state["sql"]
    dw_mysql_repository = runtime.context["dw_mysql_repository"]

    query_result = await dw_mysql_repository.run(sql)

    logger.info(
        f"SQL 执行完成：返回 {len(query_result.rows)} 行"
        + (f"（已达上限 {query_result.row_limit} 行，结果被截断）" if query_result.truncated else "")
    )
    runtime.stream_writer(
        {
            "type": "result",
            "data": query_result.rows,
            "truncated": query_result.truncated,
            "row_limit": query_result.row_limit,
        }
    )
    return None

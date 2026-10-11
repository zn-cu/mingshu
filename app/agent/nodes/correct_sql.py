import yaml
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.llm import llm
from app.agent.llm_output import strip_sql_code_fence
from app.agent.state import AgentState
from app.agent.step import step
from app.prompt.prompt_loader import load_prompt
from app.core.log import logger


@step("校正SQL")
async def correct_sql(state: AgentState, runtime: Runtime[AgentContext]):
    table_infos = state["table_infos"]
    metric_infos = state["metric_infos"]
    date_info = state["date_info"]
    db_info = state["db_info"]
    query = state["query"]
    sql = state["sql"]
    error = state["error"]

    prompt = PromptTemplate(
        template=load_prompt("correct_sql"),
        input_variables=["table_infos", "metric_infos", "date_info", "db_info", "query", "sql", "error"],
    )
    output_parser = StrOutputParser()
    chain = prompt | llm | output_parser

    result = await chain.ainvoke(
        {
            "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False),
            "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False),
            "date_info": yaml.dump(date_info, allow_unicode=True, sort_keys=False),
            "db_info": yaml.dump(db_info, allow_unicode=True, sort_keys=False),
            "query": query,
            "sql": sql,
            "error": error,
        }
    )

    logger.info(f"Corrected SQL: {result}")

    # 计数用于「最多校正几次」的限制（见 graph 里 correct_sql → validate_sql 的回边）
    return {
        "sql": strip_sql_code_fence(result),
        "sql_correction_count": int(state.get("sql_correction_count", 0)) + 1,
    }

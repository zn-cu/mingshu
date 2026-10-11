import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.llm import llm
from app.agent.llm_output import as_table_columns_map
from app.agent.state import AgentState, TableInfoState
from app.agent.step import step
from app.prompt.prompt_loader import load_prompt
from app.core.log import logger


@step("过滤表信息")
async def filter_table(state: AgentState, runtime: Runtime[AgentContext]):
    query = state["query"]
    table_infos: list[TableInfoState] = state["table_infos"]

    prompt = PromptTemplate(template=load_prompt("filter_table_info"), input_variables=["query", "table_infos"])
    output_parser = JsonOutputParser()
    chain = prompt | llm | output_parser

    result = await chain.ainvoke(
        {"query": query, "table_infos": yaml.dump(table_infos, allow_unicode=True, sort_keys=False)}
    )
    # 形状不对直接失败，避免“过滤出 0 张表”这种静默错误
    selected_columns = as_table_columns_map(result)

    filtered_table_infos: list[TableInfoState] = []
    for table_info in table_infos:
        allowed_columns = selected_columns.get(table_info["name"])
        if not allowed_columns:
            continue
        allowed = set(allowed_columns)
        # 不改动 state 里的原对象，构造新的表信息返回
        filtered_table_infos.append(
            TableInfoState(
                name=table_info["name"],
                role=table_info["role"],
                description=table_info["description"],
                columns=[
                    column_info
                    for column_info in table_info["columns"]
                    if column_info["name"] in allowed
                ],
            )
        )

    if not filtered_table_infos:
        # 全被过滤掉时，下游会拿到空 schema 并开始编造表名，所以退回过滤前的集合
        logger.warning("过滤表信息结果为空，退回使用过滤前的候选表，避免下游拿到空 schema 生成 SQL")
        filtered_table_infos = table_infos

    logger.info(f"Filtered table infos: {[item['name'] for item in filtered_table_infos]}")
    return {"table_infos": filtered_table_infos}

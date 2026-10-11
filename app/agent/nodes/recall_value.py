import asyncio

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.llm import llm
from app.agent.llm_output import as_string_list
from app.agent.state import AgentState
from app.agent.step import step
from app.entities.value_info import ValueInfo
from app.prompt.prompt_loader import load_prompt
from app.core.log import logger


@step("召回字段取值")
async def recall_value(state: AgentState, runtime: Runtime[AgentContext]):
    query = state["query"]
    keywords = state["keywords"]
    value_es_repository = runtime.context["value_es_repository"]

    prompt = PromptTemplate(template=load_prompt("extend_keywords_for_value_recall"), input_variables=["query"])
    output_parser = JsonOutputParser()
    chain = prompt | llm | output_parser

    result = await chain.ainvoke({"query": query})
    extra_keywords = as_string_list(result, field="字段取值关键词")

    # 去重且保持顺序（原来是 set，顺序随机）
    keywords = list(dict.fromkeys(keywords + extra_keywords))

    # 并发全文检索（原来是每个关键词串行等一次 ES）
    search_results = await asyncio.gather(
        *(value_es_repository.search(keyword) for keyword in keywords)
    )

    value_infos_map: dict[str, ValueInfo] = {}
    for current_value_infos in search_results:
        for current_value_info in current_value_infos:
            if current_value_info.id not in value_infos_map:
                value_infos_map[current_value_info.id] = current_value_info

    retrieved_value_infos: list[ValueInfo] = list(value_infos_map.values())
    logger.info(f"Recalled value infos: {list(value_infos_map.keys())}")
    return {"retrieved_value_infos": retrieved_value_infos}

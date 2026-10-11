import yaml
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.llm import llm
from app.agent.llm_output import as_string_list
from app.agent.state import AgentState, MetricInfoState
from app.agent.step import step
from app.prompt.prompt_loader import load_prompt
from app.core.log import logger


@step("过滤指标信息")
async def filter_metric(state: AgentState, runtime: Runtime[AgentContext]):
    query = state["query"]
    metric_infos: list[MetricInfoState] = state["metric_infos"]

    prompt = PromptTemplate(template=load_prompt("filter_metric_info"), input_variables=["query", "metric_infos"])
    output_parser = JsonOutputParser()
    chain = prompt | llm | output_parser

    result = await chain.ainvoke(
        {"query": query, "metric_infos": yaml.dump(metric_infos, allow_unicode=True, sort_keys=False)}
    )
    # 期望是指标名数组；形状不对直接失败（空数组合法：表示问题不需要指标）
    selected_names = set(as_string_list(result, field="指标名称"))

    filtered_metric_infos = [
        metric_info for metric_info in metric_infos if metric_info["name"] in selected_names
    ]

    logger.info(f"Filtered metric infos: {[item['name'] for item in filtered_metric_infos]}")
    return {"metric_infos": filtered_metric_infos}

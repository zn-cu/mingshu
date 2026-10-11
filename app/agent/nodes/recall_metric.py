import asyncio

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.llm import llm
from app.agent.llm_output import as_string_list
from app.agent.state import AgentState
from app.agent.step import step
from app.entities.metric_info import MetricInfo
from app.prompt.prompt_loader import load_prompt
from app.core.log import logger


@step("召回指标信息")
async def recall_metric(state: AgentState, runtime: Runtime[AgentContext]):
    query = state["query"]
    keywords = state["keywords"]
    embedding_client = runtime.context["embedding_client"]
    metric_qdrant_repository = runtime.context["metric_qdrant_repository"]

    prompt = PromptTemplate(template=load_prompt("extend_keywords_for_metric_recall"), input_variables=["query"])
    output_parser = JsonOutputParser()
    chain = prompt | llm | output_parser

    result = await chain.ainvoke({"query": query})
    extra_keywords = as_string_list(result, field="指标关键词")

    # 去重且保持顺序（原来是 set，顺序随机）
    keywords = list(dict.fromkeys(keywords + extra_keywords))

    # 一次批量向量化 + 并发检索
    embeddings = await embedding_client.aembed_documents(keywords)
    if len(embeddings) != len(keywords):
        raise RuntimeError(
            f"向量服务返回数量与请求不一致：请求 {len(keywords)} 条，返回 {len(embeddings)} 条"
        )

    search_results = await asyncio.gather(
        *(metric_qdrant_repository.search(embedding) for embedding in embeddings)
    )

    metric_info_map: dict[str, MetricInfo] = {}
    for current_metric_infos in search_results:
        for metric_info in current_metric_infos:
            if metric_info.id not in metric_info_map:
                metric_info_map[metric_info.id] = metric_info
    retrieved_metric_infos: list[MetricInfo] = list(metric_info_map.values())

    logger.info(f"Recalled metric infos: {list(metric_info_map.keys())}")
    return {"retrieved_metric_infos": retrieved_metric_infos}

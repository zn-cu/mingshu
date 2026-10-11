import asyncio

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.llm import llm
from app.agent.llm_output import as_string_list
from app.agent.state import AgentState
from app.agent.step import step
from app.entities.column_info import ColumnInfo
from app.prompt.prompt_loader import load_prompt
from app.core.log import logger


@step("召回字段信息")
async def recall_column(state: AgentState, runtime: Runtime[AgentContext]):
    keywords = state["keywords"]
    query = state["query"]
    column_qdrant_repository = runtime.context["column_qdrant_repository"]
    embedding_client = runtime.context["embedding_client"]

    prompt = PromptTemplate(template=load_prompt("extend_keywords_for_column_recall"), input_variables=["query"])
    output_parser = JsonOutputParser()
    chain = prompt | llm | output_parser

    result = await chain.ainvoke({"query": query})
    extra_keywords = as_string_list(result, field="字段关键词")

    # 去重且保持顺序（原来是 set，顺序随机，同一个问题每次召回顺序都不同）
    keywords = list(dict.fromkeys(keywords + extra_keywords))

    # 一次批量向量化（原来每个关键词一次 embedding 调用），数量与顺序必须对齐
    embeddings = await embedding_client.aembed_documents(keywords)
    if len(embeddings) != len(keywords):
        raise RuntimeError(
            f"向量服务返回数量与请求不一致：请求 {len(keywords)} 条，返回 {len(embeddings)} 条"
        )

    # 并发检索（原来是串行 for 循环，延迟随关键词数量线性增长）
    search_results = await asyncio.gather(
        *(column_qdrant_repository.search(embedding) for embedding in embeddings)
    )

    column_info_map: dict[str, ColumnInfo] = {}
    for current_column_infos in search_results:
        for column_info in current_column_infos:
            if column_info.id not in column_info_map:
                column_info_map[column_info.id] = column_info
    retrieved_column_infos: list[ColumnInfo] = list(column_info_map.values())

    logger.info(f"Recalled column infos: {list(column_info_map.keys())}")
    return {"retrieved_column_infos": retrieved_column_infos}

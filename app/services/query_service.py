import asyncio
import json

from langchain_openai import OpenAIEmbeddings

from app.agent.context import AgentContext
from app.agent.graph import graph
from app.agent.state import AgentState
from app.conf.app_config import app_config
from app.core.log import logger
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


class QueryService:
    def __init__(self,
                 meta_mysql_repository: MetaMySQLRepository,
                 embedding_client: OpenAIEmbeddings,
                 dw_mysql_repository: DWMySQLRepository,
                 column_qdrant_repository: ColumnQdrantRepository,
                 metric_qdrant_repository: MetricQdrantRepository,
                 value_es_repository: ValueESRepository
                 ):
        self.meta_mysql_repository = meta_mysql_repository
        self.embedding_client = embedding_client
        self.dw_mysql_repository = dw_mysql_repository

        self.column_qdrant_repository = column_qdrant_repository
        self.metric_qdrant_repository = metric_qdrant_repository
        self.value_es_repository = value_es_repository

    async def query(self, query: str):
        state = AgentState(query=query)
        context = AgentContext(column_qdrant_repository=self.column_qdrant_repository,
                                   embedding_client=self.embedding_client,
                                   metric_qdrant_repository=self.metric_qdrant_repository,
                                   value_es_repository=self.value_es_repository,
                                   meta_mysql_repository=self.meta_mysql_repository,
                                   dw_mysql_repository=self.dw_mysql_repository)

        # 整体超时：单个节点再有超时，也要防止整条链路无限期挂住
        timeout_seconds = app_config.query.request_timeout_seconds
        try:
            async with asyncio.timeout(timeout_seconds if timeout_seconds > 0 else None):
                async for chunk in graph.astream(input=state, context=context, stream_mode='custom'):
                    yield _sse(chunk)
        except TimeoutError:
            logger.error(f"查询整体超时（{timeout_seconds} 秒），已中止本次查询")
            yield _sse({"type": "error", "message": f"查询超时（超过 {timeout_seconds} 秒），已中止。"})
        except asyncio.CancelledError:
            # 客户端断开时 Starlette 会取消这个生成器，这里记录下来便于排查
            logger.info("客户端已断开连接，本次查询被取消")
            raise
        except Exception as e:
            logger.exception(f"查询失败: {e}")
            yield _sse({"type": "error", "message": str(e)})

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from langchain_openai import OpenAIEmbeddings
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import meta_mysql_client_manager, dw_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.conf.app_config import app_config
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.services.query_service import QueryService


async def require_api_key(x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> None:
    """校验查询接口的 X-API-Key。

    未配置 ``api.api_key`` 时不校验（本地开发零配置）；配置了就必须带对，
    否则任何人只要能访问到服务就能查你的数仓。比较用 ``compare_digest``，避免时序侧信道。
    """
    expected = app_config.api.api_key
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="缺少或错误的 X-API-Key")


async def get_meta_session():
    async with meta_mysql_client_manager.session_factory() as meta_session:
        yield meta_session


async def get_meta_mysql_repository(session: Annotated[AsyncSession, Depends(get_meta_session)]) -> MetaMySQLRepository:
    return MetaMySQLRepository(session)


async def get_embedding_client() -> OpenAIEmbeddings:
    return embedding_client_manager.client


async def get_dw_session():
    async with dw_mysql_client_manager.session_factory() as dw_session:
        yield dw_session


async def get_dw_mysql_repository(session: Annotated[AsyncSession, Depends(get_dw_session)]) -> DWMySQLRepository:
    return DWMySQLRepository(session)


async def get_column_qdrant_repository() -> ColumnQdrantRepository:
    return ColumnQdrantRepository(qdrant_client_manager.client)


async def get_metric_qdrant_repository() -> MetricQdrantRepository:
    return MetricQdrantRepository(qdrant_client_manager.client)


async def get_value_es_repository() -> ValueESRepository:
    return ValueESRepository(es_client_manager.client)


async def get_query_service(
        meta_mysql_repository: Annotated[MetaMySQLRepository, Depends(get_meta_mysql_repository)],
        embedding_client: Annotated[OpenAIEmbeddings, Depends(get_embedding_client)],
        dw_mysql_repository: Annotated[DWMySQLRepository, Depends(get_dw_mysql_repository)],
        column_qdrant_repository: Annotated[ColumnQdrantRepository, Depends(get_column_qdrant_repository)],
        metric_qdrant_repository: Annotated[MetricQdrantRepository, Depends(get_metric_qdrant_repository)],
        value_es_repository: Annotated[ValueESRepository, Depends(get_value_es_repository)]
) -> QueryService:
    return QueryService(
        meta_mysql_repository=meta_mysql_repository,
        embedding_client=embedding_client,
        dw_mysql_repository=dw_mysql_repository,
        column_qdrant_repository=column_qdrant_repository,
        metric_qdrant_repository=metric_qdrant_repository,
        value_es_repository=value_es_repository
    )

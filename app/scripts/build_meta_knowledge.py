import argparse
import asyncio
import sys
from pathlib import Path

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import meta_mysql_client_manager, dw_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.repositories.es.value_es_repository import ValueESRepository
from app.repositories.mysql.dw.dw_mysql_repository import DWMySQLRepository
from app.repositories.mysql.meta.meta_mysql_repository import MetaMySQLRepository
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository
from app.services.meta_knowledge_service import MetaKnowledgeService


async def build(config_path: Path):
    meta_mysql_client_manager.init()
    dw_mysql_client_manager.init()
    qdrant_client_manager.init()
    embedding_client_manager.init()
    es_client_manager.init()

    try:
        async with meta_mysql_client_manager.session_factory() as meta_session, dw_mysql_client_manager.session_factory() as dw_session:
            meta_mysql_repository = MetaMySQLRepository(meta_session)
            dw_mysql_repository = DWMySQLRepository(dw_session)

            column_qdrant_repository = ColumnQdrantRepository(qdrant_client_manager.client)

            value_es_repository = ValueESRepository(es_client_manager.client)

            metric_qdrant_repository = MetricQdrantRepository(qdrant_client_manager.client)

            meta_knowledge_service = MetaKnowledgeService(meta_mysql_repository=meta_mysql_repository,
                                                          dw_mysql_repository=dw_mysql_repository,
                                                          column_qdrant_repository=column_qdrant_repository,
                                                          embedding_client=embedding_client_manager.client,
                                                          value_es_repository=value_es_repository,
                                                          metric_qdrant_repository=metric_qdrant_repository)
            await meta_knowledge_service.build(config_path)
    finally:
        # 出错时也要释放连接，否则脚本会挂着不退出
        await meta_mysql_client_manager.close()
        await dw_mysql_client_manager.close()
        await qdrant_client_manager.close()
        await es_client_manager.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='按配置重建元知识（MySQL 元数据 + Qdrant 向量 + ES 全文索引）')
    parser.add_argument('-c', '--conf', default='conf/meta_config.yaml',
                        help='元知识配置文件路径（默认 conf/meta_config.yaml）')
    args = parser.parse_args()

    config_path = Path(args.conf)
    if not config_path.is_file():
        print(f"配置文件不存在：{config_path}", file=sys.stderr)
        sys.exit(2)

    asyncio.run(build(config_path))

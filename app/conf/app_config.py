# 日志配置
from dataclasses import dataclass, field
from pathlib import Path

from omegaconf import OmegaConf


@dataclass
class File:
    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class Console:
    enable: bool
    level: str


@dataclass
class LoggingConfig:
    file: File
    console: Console


# 数据库配置
@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass
class QdrantConfig:
    host: str
    port: int
    embedding_size: int


@dataclass
class EmbeddingConfig:
    host: str
    port: int
    model: str
    # 单次向量化调用的超时（秒）。SDK 默认 600 秒，向量服务挂住会把一次查询拖到十几分钟
    timeout_seconds: int = 30


@dataclass
class ESConfig:
    host: str
    port: int
    index_name: str


@dataclass
class LLMConfig:
    model_name: str
    api_key: str
    base_url: str
    # 单次模型调用的超时（秒）与重试次数。
    # 注意预算关系：最坏情况 = timeout_seconds × (1 + max_retries) + 退避，
    # 应小于 query.request_timeout_seconds，否则挂住时先触发的是「整体超时」而不是模型超时。
    timeout_seconds: int = 45
    max_retries: int = 2


@dataclass
class QueryConfig:
    """查询侧的安全与资源限制。"""

    # 单次查询最多返回多少行，0 表示不限制
    row_limit: int = 1000
    # 单条 SQL 在数据库端的执行时间上限（毫秒），0 表示不限制
    sql_timeout_ms: int = 30000
    # 一次问答（整张图）的整体超时（秒），0 表示不限制
    request_timeout_seconds: int = 180


@dataclass
class AgentConfig:
    """智能体流程相关配置。"""

    # SQL 校验失败后最多自动校正几次（每次校正 = 一次大模型调用）；0 表示不校正
    max_sql_corrections: int = 2


@dataclass
class APIConfig:
    """对外接口的安全与探针行为。"""

    # 接口鉴权：留空 = 不校验（本地开发默认）；填了之后 /api/query 必须带 X-API-Key
    api_key: str = ""
    # 允许跨域的来源；留空 = 不启用 CORS（开发时前端走 Vite 代理，用不到 CORS）
    cors_origins: list[str] = field(default_factory=list)
    # /ready 中「向量服务」这项的缓存秒数（该项会真的发一次向量化请求，健康检查没必要每次都打）
    ready_cache_seconds: int = 60


@dataclass
class AppConfig:
    logging: LoggingConfig
    db_meta: DBConfig
    db_dw: DBConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    es: ESConfig
    llm: LLMConfig
    query: QueryConfig = field(default_factory=QueryConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    api: APIConfig = field(default_factory=APIConfig)


# 配置文件路径：默认 conf/app_config.yaml；可用 DA_CONFIG_FILE 覆盖
import os

config_file = Path(os.environ.get("DA_CONFIG_FILE") or Path(__file__).parents[2] / 'conf' / 'app_config.yaml')
context = OmegaConf.load(config_file)

# 本地覆盖：conf/app_config.local.yaml（已被 .gitignore 排除）
# 仓库里提交的是脱敏版 app_config.yaml，真实密钥放这里，本地就不必依赖环境变量。
local_file = config_file.with_name("app_config.local.yaml")
if local_file.is_file():
    context = OmegaConf.merge(context, OmegaConf.load(local_file))

schema = OmegaConf.structured(AppConfig)
app_config: AppConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))

if __name__ == '__main__':
    print(app_config.logging.file.path)
    print(app_config.query)

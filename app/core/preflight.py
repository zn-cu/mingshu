"""启动自检。

lifespan 里做的只是「构造客户端对象」，而 Qdrant / ES / MySQL / 向量服务都是懒连接，
所以配置写错、容器没起来、向量维度不匹配这类问题，要等到用户提问那一刻才暴露，
报错还往往很难懂（比如 Qdrant 里集合不存在，前端只会看到一句搜索失败）。

这里在启动时主动探一遍并写日志，同时把结果通过 GET /ready 暴露出去，
方便部署时判断「服务起来了没有」和「依赖都通不通」。
"""

from dataclasses import dataclass
import time
from urllib.parse import urlparse

from sqlalchemy import text

from app.clients.embedding_client_manager import embedding_client_manager
from app.clients.es_client_manager import es_client_manager
from app.clients.mysql_client_manager import meta_mysql_client_manager, dw_mysql_client_manager
from app.clients.qdrant_client_manager import qdrant_client_manager
from app.conf.app_config import app_config
from app.core.log import logger
from app.repositories.qdrant.column_qdrant_repository import ColumnQdrantRepository
from app.repositories.qdrant.metric_qdrant_repository import MetricQdrantRepository


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


async def _check_mysql(name: str, manager) -> CheckResult:
    if manager.engine is None:
        return CheckResult(name, False, "客户端未初始化")
    try:
        async with manager.session_factory() as session:
            version = (await session.execute(text("select version()"))).scalar()
        return CheckResult(name, True, f"MySQL {version}")
    except Exception as e:
        return CheckResult(name, False, f"{type(e).__name__}: {e}")


async def _check_qdrant() -> list[CheckResult]:
    if qdrant_client_manager.client is None:
        return [CheckResult("qdrant", False, "客户端未初始化")]

    expected_size = app_config.qdrant.embedding_size
    results: list[CheckResult] = []
    # 集合名直接取自仓库类，避免这里再写一遍字面量而与实现漂移
    targets = (
        ("qdrant:字段向量", ColumnQdrantRepository),
        ("qdrant:指标向量", MetricQdrantRepository),
    )
    for name, repository_class in targets:
        collection = repository_class.collection_name
        try:
            if not await qdrant_client_manager.client.collection_exists(collection):
                results.append(CheckResult(name, False, f"集合 {collection} 不存在，请先执行元知识构建脚本"))
                continue
            info = await qdrant_client_manager.client.get_collection(collection)
            size = info.config.params.vectors.size
            if size != expected_size:
                results.append(CheckResult(
                    name, False, f"{collection} 向量维度 {size} 与配置的 embedding_size={expected_size} 不一致"
                ))
            else:
                results.append(CheckResult(name, True, f"{collection}，{size} 维"))
        except Exception as e:
            results.append(CheckResult(name, False, f"{type(e).__name__}: {e}"))
    return results


async def _check_es() -> CheckResult:
    if es_client_manager.client is None:
        return CheckResult("elasticsearch", False, "客户端未初始化")

    index_name = app_config.es.index_name
    try:
        if not await es_client_manager.client.indices.exists(index=index_name):
            return CheckResult(
                "elasticsearch", False, f"索引 {index_name} 不存在，请先执行元知识构建脚本"
            )
        count = (await es_client_manager.client.count(index=index_name))["count"]
        return CheckResult("elasticsearch", True, f"索引 {index_name}，{count} 条文档")
    except Exception as e:
        return CheckResult("elasticsearch", False, f"{type(e).__name__}: {e}")


class _TtlResultCache:
    """极简 TTL 缓存（只给「向量服务」这一项用）。"""

    def __init__(self) -> None:
        self._result: CheckResult | None = None
        self._expires_at: float = 0.0

    def get(self) -> CheckResult | None:
        if self._result is not None and time.monotonic() < self._expires_at:
            return self._result
        return None

    def set(self, result: CheckResult, ttl: float) -> None:
        self._result = result
        self._expires_at = time.monotonic() + ttl


_embedding_check_cache = _TtlResultCache()

# 失败时缓存更短：否则刚把向量服务修好，还要等一整个 TTL 才能看到 /ready 恢复
_FAILED_CACHE_SECONDS = 10


async def _check_embedding() -> CheckResult:
    """探测向量服务（带 TTL 缓存）。

    这一项会真的发一次向量化请求；而 /ready 可能被负载均衡每秒探一次，
    其余几项都是廉价查询，所以只给它加缓存（见 api.ready_cache_seconds）。
    """
    ttl = float(app_config.api.ready_cache_seconds)
    if ttl > 0:
        cached = _embedding_check_cache.get()
        if cached is not None:
            return cached

    result = await _probe_embedding()

    if ttl > 0:
        _embedding_check_cache.set(result, ttl if result.ok else min(ttl, _FAILED_CACHE_SECONDS))
    return result


async def _probe_embedding() -> CheckResult:
    if embedding_client_manager.client is None:
        return CheckResult("embedding", False, "客户端未初始化")

    expected_size = app_config.qdrant.embedding_size
    try:
        vector = await embedding_client_manager.client.aembed_query("ping")
        if len(vector) != expected_size:
            return CheckResult(
                "embedding", False, f"实际返回 {len(vector)} 维，配置的 embedding_size={expected_size}"
            )
        return CheckResult("embedding", True, f"{len(vector)} 维")
    except Exception as e:
        return CheckResult("embedding", False, f"{type(e).__name__}: {e}")


def _check_llm() -> CheckResult:
    """检查大模型配置是否齐全。

    只判断「有没有配」，**不校验密钥是否有效** —— 那需要真的调一次模型，
    健康检查不该为此花钱（密钥写错时会在第一次提问时报错，信息也很明确）。
    但「压根没配」是最常见的部署疏漏，必须让它一眼可见，而不是等用户提问才发现。

    注意：api_key 为空时 app/agent/llm.py 会用占位值构造客户端（否则 import 就失败），
    所以这里不会因为缺密钥而起不来，只是所有提问都会失败 —— 更需要自检点出来。
    """
    model_name = (app_config.llm.model_name or "").strip()
    base_url = (app_config.llm.base_url or "").strip()
    api_key = (app_config.llm.api_key or "").strip()

    missing = []
    if not api_key:
        missing.append("llm.api_key")
    if not model_name:
        missing.append("llm.model_name")
    if not base_url:
        missing.append("llm.base_url")

    if missing:
        return CheckResult(
            "llm",
            False,
            f"未配置 {'、'.join(missing)}：提问会失败。"
            f"请写进 conf/app_config.local.yaml，或设置环境变量 DA_LLM_API_KEY",
        )

    return CheckResult("llm", True, f"{model_name} @ {urlparse(base_url).netloc or base_url}")


async def check_dependencies() -> list[CheckResult]:
    """逐个探测外部依赖，返回每一项的结果（不抛异常）。"""
    results: list[CheckResult] = [
        await _check_mysql("mysql:meta", meta_mysql_client_manager),
        await _check_mysql("mysql:dw", dw_mysql_client_manager),
    ]
    results.extend(await _check_qdrant())
    results.append(await _check_es())
    results.append(await _check_embedding())
    results.append(_check_llm())
    return results


async def run_startup_preflight() -> bool:
    """启动时跑一遍自检并写日志；返回是否全部通过。

    不通过也**不阻止启动**：本地开发时常常先起服务后起容器，硬失败反而更难用。
    真正的门禁交给 GET /ready（未通过返回 503）。
    """
    try:
        results = await check_dependencies()
    except Exception as e:
        logger.exception(f"启动自检执行失败: {e}")
        return False

    for result in results:
        if result.ok:
            logger.info(f"自检通过  | {result.name:<28} | {result.detail}")
        else:
            logger.warning(f"自检未通过 | {result.name:<28} | {result.detail}")

    failed = [result for result in results if not result.ok]
    if failed:
        logger.warning(f"启动自检：{len(failed)}/{len(results)} 项未通过，服务仍会启动；GET /ready 可查看详情")
        return False

    logger.info(f"启动自检全部通过（{len(results)} 项）")
    return True

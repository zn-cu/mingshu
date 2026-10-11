from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.preflight import check_dependencies

health_router = APIRouter(tags=["健康检查"])


@health_router.get("/health", summary="存活探针")
async def health():
    """只表示进程活着，不访问任何外部依赖。"""
    return {"status": "ok"}


@health_router.get("/ready", summary="就绪探针")
async def ready():
    """检查外部依赖（两个 MySQL、Qdrant、ES、向量服务）是否可用。

    全部通过返回 200；有任何一项不通过返回 503，并在 checks 里说明原因。
    """
    results = await check_dependencies()
    failed = [result for result in results if not result.ok]
    return JSONResponse(
        status_code=200 if not failed else 503,
        content={
            "status": "ok" if not failed else "degraded",
            "checks": [
                {"name": result.name, "ok": result.ok, "detail": result.detail}
                for result in results
            ],
        },
    )

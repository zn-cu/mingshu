import time
import uuid
import warnings

# jieba（分词库）内部几个正则字面量会触发 SyntaxWarning（invalid escape sequence），
# 与我们的代码无关，但每次启动都会往日志里刷一屏。
# 这里按消息类型收窄屏蔽：编译期警告不带模块名，所以只能按消息匹配，不能按 module 过滤。
warnings.filterwarnings("ignore", category=SyntaxWarning, message=r"invalid escape sequence.*")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.lifespan import lifespan
from app.api.routers.health_router import health_router
from app.api.routers.query_router import query_router
from app.conf.app_config import app_config
from app.core.context import request_id_context_var


def setup_cors(application: FastAPI, origins: list[str]) -> None:
    """按配置启用跨域。

    来源列表留空就**不启用**：开发时前端走 Vite 代理（同源），根本用不到 CORS；
    只有把前端构建产物部署到别的域名/端口时才需要按需放行。
    """
    if not origins:
        return
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
        expose_headers=["X-Request-ID", "X-Process-Time"],
    )


app = FastAPI(lifespan=lifespan)
setup_cors(app, app_config.api.cors_origins)

app.include_router(query_router)
app.include_router(health_router)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    """给每个请求生成 request_id（日志里可追踪），并把 request_id 与耗时回写到响应头。

    原来的函数名叫 add_process_time_header，但实际上什么都没加；现在名副其实。
    """
    request_id = str(uuid.uuid4())
    request_id_context_var.set(request_id)

    started = time.perf_counter()
    response = await call_next(request)

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{(time.perf_counter() - started) * 1000:.1f}ms"
    return response

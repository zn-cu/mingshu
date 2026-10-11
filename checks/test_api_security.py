"""接口安全：X-API-Key 鉴权与 CORS。

鉴权：`api.api_key` 留空 = 不校验（本地开发零配置），填了就必须带对。
CORS：来源留空 = 不启用（开发走 Vite 代理同源），填了才放行指定来源。
"""

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import require_api_key
from app.conf.app_config import app_config
from main import app, setup_cors


@pytest.mark.anyio
async def test_dependency_allows_everything_when_unconfigured(monkeypatch):
    monkeypatch.setattr(app_config.api, "api_key", "")

    await require_api_key(None)
    await require_api_key("随便什么值")


@pytest.mark.anyio
async def test_dependency_requires_matching_key(monkeypatch):
    monkeypatch.setattr(app_config.api, "api_key", "s3cret")

    await require_api_key("s3cret")

    for bad in (None, "", "wrong", "s3cres"):
        with pytest.raises(HTTPException) as excinfo:
            await require_api_key(bad)
        assert excinfo.value.status_code == 401


@pytest.mark.anyio
async def test_query_endpoint_rejects_missing_key(monkeypatch):
    """接口层面确实挂上了依赖（不是只测了函数）。"""
    monkeypatch.setattr(app_config.api, "api_key", "s3cret")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/query", json={"query": "统计销售额"})
        assert resp.status_code == 401
        assert "X-API-Key" in resp.json()["detail"]


@pytest.mark.anyio
async def test_health_endpoint_never_requires_key(monkeypatch):
    """探针不鉴权：负载均衡不该因为缺密钥就把实例判死。"""
    monkeypatch.setattr(app_config.api, "api_key", "s3cret")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/health")).status_code == 200


def _cors_middlewares(application: FastAPI):
    return [m for m in application.user_middleware if m.cls is CORSMiddleware]


def test_cors_not_enabled_by_default():
    application = FastAPI()
    setup_cors(application, [])

    assert _cors_middlewares(application) == []


def test_cors_enabled_when_origins_configured():
    application = FastAPI()
    setup_cors(application, ["http://localhost:5173"])

    assert len(_cors_middlewares(application)) == 1


@pytest.mark.anyio
async def test_cors_preflight_is_answered():
    application = FastAPI()
    setup_cors(application, ["http://localhost:5173"])

    @application.get("/ping")
    async def ping():
        return {"ok": True}

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/ping",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"

        # 未在名单里的来源不应被放行
        other = await client.options(
            "/ping",
            headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" not in other.headers

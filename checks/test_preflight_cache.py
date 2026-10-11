"""就绪探针里「向量服务」那项的 TTL 缓存（app/core/preflight.py）。

/ready 可能被负载均衡每秒探一次，而这一项会真的发一次向量化请求；
其余几项都是廉价查询，所以只缓存它。
"""

import pytest

from app.clients.embedding_client_manager import embedding_client_manager
from app.conf.app_config import app_config
from app.core import preflight


class _FakeEmbedding:
    def __init__(self, dimensions: int, error: Exception | None = None):
        self.dimensions = dimensions
        self.error = error
        self.calls = 0

    async def aembed_query(self, _text):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return [0.0] * self.dimensions


class _FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def environment(monkeypatch):
    """每个用例都拿到干净的缓存、可控的时钟与假的向量客户端。"""
    clock = _FakeClock()
    monkeypatch.setattr(preflight, "time", clock)
    monkeypatch.setattr(preflight, "_embedding_check_cache", preflight._TtlResultCache())
    monkeypatch.setattr(app_config.api, "ready_cache_seconds", 60)
    client = _FakeEmbedding(app_config.qdrant.embedding_size)
    monkeypatch.setattr(embedding_client_manager, "client", client)
    return clock, client


@pytest.mark.anyio
async def test_success_is_cached_within_ttl(environment):
    clock, client = environment

    first = await preflight._check_embedding()
    second = await preflight._check_embedding()
    clock.advance(59)
    third = await preflight._check_embedding()

    assert first.ok and second.ok and third.ok
    assert client.calls == 1, "TTL 内不该重复请求向量服务"


@pytest.mark.anyio
async def test_reprobes_after_ttl(environment):
    clock, client = environment

    await preflight._check_embedding()
    clock.advance(61)
    await preflight._check_embedding()

    assert client.calls == 2


@pytest.mark.anyio
async def test_cache_can_be_disabled(environment, monkeypatch):
    _, client = environment
    monkeypatch.setattr(app_config.api, "ready_cache_seconds", 0)

    await preflight._check_embedding()
    await preflight._check_embedding()

    assert client.calls == 2


@pytest.mark.anyio
async def test_failure_is_cached_shorter_than_success(environment, monkeypatch):
    """失败缓存更短：刚把向量服务修好，不该还要等一整个 TTL 才恢复。"""
    clock, _ = environment
    failing = _FakeEmbedding(0, error=RuntimeError("tei 挂了"))
    monkeypatch.setattr(embedding_client_manager, "client", failing)

    assert (await preflight._check_embedding()).ok is False
    clock.advance(11)  # 超过失败缓存（10 秒），但远没到 60 秒
    wait_again = await preflight._check_embedding()

    assert wait_again.ok is False
    assert failing.calls == 2, "失败结果应在较短时间后重新探测"


@pytest.mark.anyio
async def test_dimension_mismatch_is_reported(environment, monkeypatch):
    wrong = _FakeEmbedding(512)
    monkeypatch.setattr(embedding_client_manager, "client", wrong)

    result = await preflight._check_embedding()

    assert result.ok is False
    assert "512" in result.detail and str(app_config.qdrant.embedding_size) in result.detail

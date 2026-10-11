"""自检里的模型配置检查（app/core/preflight.py 的 _check_llm）。

只在「配置是否齐全」这一层判断，不校验密钥有效性（那要真调一次模型，健康检查不该花钱）。
重点是让「压根没配密钥」这种部署疏漏在启动日志与 /ready 里一眼可见，
而不是等用户提问时才报 401。
"""

import pytest

from app.conf.app_config import app_config
from app.core import preflight


@pytest.fixture
def llm_config(monkeypatch):
    """每个用例都在完整配置的基础上改，避免互相影响。"""
    monkeypatch.setattr(app_config.llm, "model_name", "qwen3.8-flash")
    monkeypatch.setattr(app_config.llm, "base_url", "https://example.com/compatible-mode/v1")
    monkeypatch.setattr(app_config.llm, "api_key", "sk-test")
    return app_config.llm


def test_reports_missing_api_key(llm_config, monkeypatch):
    monkeypatch.setattr(app_config.llm, "api_key", "")

    result = preflight._check_llm()

    assert result.ok is False
    assert "llm.api_key" in result.detail
    assert "conf/app_config.local.yaml" in result.detail


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_key_or_whitespace_counts_as_missing(llm_config, monkeypatch, blank):
    monkeypatch.setattr(app_config.llm, "api_key", blank)

    assert preflight._check_llm().ok is False


def test_reports_missing_model_name(llm_config, monkeypatch):
    monkeypatch.setattr(app_config.llm, "model_name", "")

    result = preflight._check_llm()

    assert result.ok is False
    assert "llm.model_name" in result.detail


def test_reports_missing_base_url(llm_config, monkeypatch):
    monkeypatch.setattr(app_config.llm, "base_url", "")

    result = preflight._check_llm()

    assert result.ok is False
    assert "llm.base_url" in result.detail


def test_lists_every_missing_field(llm_config, monkeypatch):
    monkeypatch.setattr(app_config.llm, "api_key", "")
    monkeypatch.setattr(app_config.llm, "model_name", "")

    detail = preflight._check_llm().detail

    assert "llm.api_key" in detail and "llm.model_name" in detail


def test_passes_when_configured(llm_config):
    result = preflight._check_llm()

    assert result.ok is True
    assert "qwen3.8-flash" in result.detail
    assert "example.com" in result.detail
    # 不应把密钥本身写进探针输出
    assert "sk-test" not in result.detail


@pytest.mark.anyio
async def test_llm_is_part_of_readiness_checks(llm_config, monkeypatch):
    """/ready 的检查列表里必须有 llm 这一项（其余几项换成假的，保持用例不依赖外部服务）。"""

    async def fake_mysql(name, manager):
        return preflight.CheckResult(name, True, "fake")

    async def fake_qdrant():
        return [preflight.CheckResult("qdrant", True, "fake")]

    async def fake_es():
        return preflight.CheckResult("elasticsearch", True, "fake")

    async def fake_embedding():
        return preflight.CheckResult("embedding", True, "fake")

    monkeypatch.setattr(preflight, "_check_mysql", fake_mysql)
    monkeypatch.setattr(preflight, "_check_qdrant", fake_qdrant)
    monkeypatch.setattr(preflight, "_check_es", fake_es)
    monkeypatch.setattr(preflight, "_check_embedding", fake_embedding)

    results = await preflight.check_dependencies()
    names = [result.name for result in results]

    assert names == ["mysql:meta", "mysql:dw", "qdrant", "elasticsearch", "embedding", "llm"]
    assert results[-1].ok is True

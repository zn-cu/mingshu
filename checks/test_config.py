"""配置加载：新增字段的默认值、旧配置兼容、环境变量注入、脱敏约束。"""

import re
from pathlib import Path

import yaml
from omegaconf import OmegaConf

from app.conf.app_config import AppConfig, app_config, config_file

PROJECT_ROOT = Path(__file__).parents[1]


def test_query_section_has_safe_defaults():
    assert app_config.query.row_limit > 0
    assert app_config.query.sql_timeout_ms > 0
    assert app_config.query.request_timeout_seconds > 0


def test_llm_timeouts_are_configured():
    """单次模型调用必须有超时，否则挂住时请求会一直悬着。"""
    assert app_config.llm.timeout_seconds > 0
    assert app_config.llm.max_retries >= 0


def test_llm_retry_budget_fits_in_request_timeout():
    """模型超时也会重试，所以最坏耗时必须小于整体超时。

    否则模型挂住时先触发的是笼统的「查询超时」，看不到「模型超时」这个真正的原因。
    """
    worst_case = app_config.llm.timeout_seconds * (1 + app_config.llm.max_retries)
    assert worst_case < app_config.query.request_timeout_seconds


def test_embedding_call_has_timeout():
    """向量化调用必须显式设超时：SDK 默认是 600 秒。"""
    assert 0 < app_config.embedding.timeout_seconds <= app_config.query.request_timeout_seconds


def test_old_config_without_new_sections_still_loads():
    """老配置文件里没有 query / agent 段、llm 里也没有新增字段，也必须能启动。"""
    raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    raw.pop("query", None)
    raw.pop("agent", None)
    raw["llm"].pop("timeout_seconds", None)
    raw["llm"].pop("max_retries", None)
    raw["embedding"].pop("timeout_seconds", None)

    merged = OmegaConf.to_object(
        OmegaConf.merge(OmegaConf.structured(AppConfig), OmegaConf.create(raw))
    )

    assert merged.query.row_limit == 1000
    assert merged.agent.max_sql_corrections == 2
    assert merged.llm.max_retries == 2
    # 默认超时要与预算约束一致（见 test_llm_retry_budget_fits_in_request_timeout）
    assert merged.llm.timeout_seconds == app_config.llm.timeout_seconds
    assert merged.embedding.timeout_seconds == app_config.embedding.timeout_seconds


def test_env_interpolation_for_secrets(monkeypatch):
    """密钥可以写成 ${oc.env:...}，配置本身就不必带密。"""
    monkeypatch.setenv("DA_TEST_API_KEY", "sk-from-env")
    raw = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    raw["llm"]["api_key"] = "${oc.env:DA_TEST_API_KEY}"

    merged = OmegaConf.to_object(
        OmegaConf.merge(OmegaConf.structured(AppConfig), OmegaConf.create(raw))
    )

    assert merged.llm.api_key == "sk-from-env"


def test_committed_config_is_sanitized():
    """仓库里提交的 conf/app_config.yaml 必须不含真实凭据。

    回归用例：这个文件曾经明文带着数据库密码与 API Key。
    这里只做结构化断言（不写任何真实值作为字面量，否则测试文件本身就成了泄露点）。
    """
    text = (PROJECT_ROOT / "conf" / "app_config.yaml").read_text(encoding="utf-8")
    raw = yaml.safe_load(text)

    # 敏感字段必须走环境变量注入，而不是写死字面量
    assert "${oc.env:" in raw["llm"]["api_key"]
    assert "${oc.env:" in raw["db_meta"]["password"]
    assert "${oc.env:" in raw["db_dw"]["password"]

    # 不允许出现像真实 API Key 的字面量（sk- 开头 + 足够长的密钥串）
    assert re.search(r"sk-[A-Za-z0-9._-]{16,}", text) is None


def test_committed_config_loads_standalone():
    """脱敏版必须能独立加载（CI / 新克隆的环境没有 local 覆盖文件）。"""
    merged = OmegaConf.to_object(
        OmegaConf.merge(
            OmegaConf.structured(AppConfig),
            OmegaConf.load(str(PROJECT_ROOT / "conf" / "app_config.yaml")),
        )
    )

    assert merged.query.row_limit == 1000
    assert merged.db_dw.user  # 默认就是只读账号名
    assert merged.llm.api_key == ""  # 没配环境变量时为空，而不是某个真实 key


def test_local_override_file_is_gitignored():
    """本地覆盖文件必须被 .gitignore 排除，否则真实密钥会被提交。"""
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "conf/*.local.yaml" in gitignore
    assert "\nconf/\n" not in gitignore  # 整个 conf/ 不能被忽略，脱敏版要进仓库


def test_es_index_name_is_read_from_config():
    """回归：索引名必须来自配置。

    曾经配置里写着 es.index_name，而仓库代码硬编码 "value_index"，两者不一致 ——
    启动自检据此误报「索引不存在」。这个用例保证两者不会再分叉。
    """
    from app.repositories.es.value_es_repository import ValueESRepository

    assert ValueESRepository(client=None).index_name == app_config.es.index_name

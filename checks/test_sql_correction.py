"""SQL 校正流程（app/agent/nodes/validate_sql.py 的预算控制）。

对应两个真实缺陷：
1. 原来校验失败后只校正一次，且 ``correct_sql → run_sql`` 意味着**校正结果不再校验**
   就被执行 —— 一条仍然语法错误的 SQL 会直接发到数仓，用户看到的是数据库报错，
   而不是「自动校正没成功」。
2. 校正次数写死在图里，改不了。

现在：校正后回到 validate_sql 重新校验，次数由 ``agent.max_sql_corrections`` 控制，
次数用完仍不通过则抛 :class:`SQLCorrectionExhausted`，不会执行未通过校验的 SQL。
"""

import pytest
from sqlalchemy.exc import OperationalError

from app.agent.nodes.validate_sql import SQLCorrectionExhausted, validate_sql
from app.core.sql_guard import UnsafeSQLError


class _FakeWriter:
    def __init__(self):
        self.events = []

    def __call__(self, event):
        self.events.append(event)


class _FakeRuntime:
    def __init__(self, repository):
        self.context = {"dw_mysql_repository": repository}
        self.stream_writer = _FakeWriter()


class _FailingRepository:
    """validate() 永远失败，用来观察预算控制。"""

    def __init__(self, error):
        self.error = error
        self.calls = 0

    async def validate(self, sql):
        self.calls += 1
        raise self.error


@pytest.mark.anyio
async def test_retries_while_budget_remains():
    repository = _FailingRepository(UnsafeSQLError("不是只读查询"))
    runtime = _FakeRuntime(repository)

    result = await validate_sql({"sql": "delete from t", "sql_correction_count": 0}, runtime)

    assert result["error"], "应把错误写回 state 交给 correct_sql"
    assert repository.calls == 1
    # 上报的成功/失败事件由 step 装饰器负责，这里确认节点自己没有吞掉异常
    assert runtime.stream_writer.events[-1]["status"] == "success"


@pytest.mark.anyio
async def test_raises_when_budget_exhausted():
    repository = _FailingRepository(UnsafeSQLError("不是只读查询"))
    runtime = _FakeRuntime(repository)

    with pytest.raises(SQLCorrectionExhausted) as excinfo:
        await validate_sql({"sql": "delete from t", "sql_correction_count": 2}, runtime)

    assert "已自动校正 2 次" in str(excinfo.value)
    assert runtime.stream_writer.events[-1]["status"] == "error"
    assert repository.calls == 1


@pytest.mark.anyio
async def test_sql_level_error_counts_toward_budget():
    """1054（未知字段）属于 SQL 问题 → 继续校正；预算用完则报错。"""
    error = OperationalError("explain select 1", {}, Exception(1054, "Unknown column"))
    runtime = _FakeRuntime(_FailingRepository(error))

    result = await validate_sql({"sql": "select bad from t", "sql_correction_count": 1}, runtime)
    assert "1054" in result["error"]

    with pytest.raises(SQLCorrectionExhausted):
        await validate_sql({"sql": "select bad from t", "sql_correction_count": 2}, runtime)


@pytest.mark.anyio
async def test_infrastructure_error_is_not_corrected():
    """数据库不可用不是 SQL 的错，直接上抛，不去浪费模型调用。"""
    error = OperationalError("select 1", {}, Exception(2003, "Can't connect"))
    repository = _FailingRepository(error)
    runtime = _FakeRuntime(repository)

    with pytest.raises(OperationalError):
        await validate_sql({"sql": "select 1", "sql_correction_count": 0}, runtime)


@pytest.mark.anyio
async def test_max_sql_corrections_default_and_overridable(monkeypatch):
    from app.conf.app_config import app_config

    assert app_config.agent.max_sql_corrections == 2

    monkeypatch.setattr(app_config.agent, "max_sql_corrections", 0)
    runtime = _FakeRuntime(_FailingRepository(UnsafeSQLError("不是只读查询")))
    with pytest.raises(SQLCorrectionExhausted):
        await validate_sql({"sql": "delete from t", "sql_correction_count": 0}, runtime)

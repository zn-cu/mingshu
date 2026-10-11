"""数据库错误分类（app/core/db_errors.py）。

这是踩过的坑：MySQL 的 errno 与 SQLAlchemy 的异常类不是一一对应的 ——
1054「未知字段」和 2003「连不上」**都是 OperationalError**。
只用异常类判断，就会把最常见的「字段名写错」当成数据库故障，
从而跳过 SQL 校正流程（比不修还糟）。所以这里按 errno 分类，并把这些真实错误码固化成用例。

errno 取值来自对本地 MySQL 8.0 的实测。
"""

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.db_errors import error_summary, is_infrastructure_error, mysql_errno


def make_db_error(errno: int, cls=OperationalError):
    orig = Exception(errno, "mock db error")
    return cls("select 1", {}, orig)


def test_mysql_errno_reads_original_exception():
    assert mysql_errno(make_db_error(1054)) == 1054


def test_mysql_errno_returns_none_without_errno():
    assert mysql_errno(ValueError("no errno here")) is None


@pytest.mark.parametrize(
    ("errno", "cls", "label"),
    [
        (1054, OperationalError, "unknown-column"),  # 实测是 OperationalError
        (1064, ProgrammingError, "syntax-error"),
        (1146, ProgrammingError, "unknown-table"),
        (1142, OperationalError, "command-denied"),
    ],
)
def test_sql_level_errors_are_not_infrastructure(errno, cls, label):
    """这些是 SQL 自身的问题，必须继续走「校正 SQL」分支。"""
    assert is_infrastructure_error(make_db_error(errno, cls)) is False


@pytest.mark.parametrize(
    "errno",
    [
        2003,  # Can't connect to MySQL server
        2013,  # Lost connection during query
        1045,  # Access denied（连接层）
        1205,  # Lock wait timeout
        1213,  # Deadlock
        3024,  # max_execution_time 触发
    ],
)
def test_infrastructure_errors_are_recognized(errno):
    """这些不是 SQL 的错，触发校正只会白烧模型调用，应直接失败。"""
    assert is_infrastructure_error(make_db_error(errno)) is True


def test_unknown_errno_is_treated_as_sql_problem():
    """取不到已知错误码时按 SQL 问题处理，与改造前行为一致，避免漏掉真正的 SQL 错误。"""
    assert is_infrastructure_error(make_db_error(99999)) is False


def test_error_summary_prefers_dbapi_message():
    """给用户看的错误说明应取底层数据库消息，而不是 SQLAlchemy 那一长串包装。"""
    error = make_db_error(1054)
    assert error_summary(error) == "(1054, 'mock db error')"


def test_error_summary_is_single_line_and_bounded():
    class Long:
        def __str__(self):
            return "第一行\n第二行\n第三行" + "x" * 400

    summary = error_summary(Long())
    assert "\n" not in summary
    assert len(summary) <= 303


def test_error_summary_falls_back_to_exception_type():
    class Silent(Exception):
        def __str__(self):
            return ""

    assert error_summary(Silent()) == "Silent"

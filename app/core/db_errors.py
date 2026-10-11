"""数据库错误分类：区分“SQL 自己有问题”和“数据库不可用”。

MySQL 的错误码与 SQLAlchemy 的异常类**不是**一一对应的（实测）：

    1054 未知字段   -> OperationalError    ← 和“连不上数据库”同一个类
    1064 语法错误   -> ProgrammingError
    1146 表不存在   -> ProgrammingError
    2003 连接被拒   -> OperationalError

所以只看异常类会把“字段名写错”误判成“数据库故障”，从而跳过 SQL 校正流程。
这里改成按 errno 分类：**只有明确属于连接/权限/资源问题的错误码才算基础设施故障，
其余一律当作 SQL 本身的问题**（也就是改造前的行为，不会让校正流程失效）。
"""

from __future__ import annotations

__all__ = ["INFRASTRUCTURE_ERRNOS", "mysql_errno", "is_infrastructure_error", "error_summary"]

# 连接、权限、服务端不可用
_CONNECTION_ERRNOS = frozenset(
    {
        1040,  # Too many connections
        1043,  # Bad handshake
        1044,  # Access denied for user to database
        1045,  # Access denied for user
        1129,  # Host is blocked
        1130,  # Host is not allowed to connect
        2002,  # Can't connect to local server
        2003,  # Can't connect to MySQL server
        2005,  # Unknown MySQL server host
        2006,  # MySQL server has gone away
        2013,  # Lost connection to MySQL server during query
        2026,  # SSL connection error
    }
)

# 资源争用与超时
_RESOURCE_ERRNOS = frozenset(
    {
        1205,  # Lock wait timeout exceeded
        1213,  # Deadlock found when trying to get lock
        3024,  # Query execution was interrupted (max_execution_time)
    }
)

INFRASTRUCTURE_ERRNOS = _CONNECTION_ERRNOS | _RESOURCE_ERRNOS


def mysql_errno(error: BaseException) -> int | None:
    """尽量取出 MySQL 错误码；SQLAlchemy 会把 DBAPI 错误包在 ``orig`` 里。"""
    for candidate in (getattr(error, "orig", None), error):
        args = getattr(candidate, "args", None)
        if args and isinstance(args[0], int):
            return args[0]
    return None


def is_infrastructure_error(error: BaseException) -> bool:
    """是否是“数据库不可用 / 资源不足”这类与 SQL 本身无关的错误。

    取不到错误码时返回 False，即按 SQL 问题处理 —— 与改造前“任何异常都走校正”
    的行为一致，宁可多花一次模型调用，也不要漏掉真正的 SQL 错误。
    """
    errno = mysql_errno(error)
    if errno is None:
        return False
    return errno in INFRASTRUCTURE_ERRNOS


def error_summary(error: BaseException, limit: int = 300) -> str:
    """取一句能给人看的错误说明。

    SQLAlchemy 的异常字符串带 SQL 原文和文档链接（``[SQL: ...]`` / ``(Background on
    this error at: ...)``），直接塞进给用户的提示会很长也很难读；底层 DBAPI 异常的
    ``orig`` 才是“Unknown column 'x' in 'field list'”这种真正有用的信息。
    """
    raw = str(getattr(error, "orig", None) or error).strip()
    first_line = raw.splitlines()[0] if raw else type(error).__name__
    return first_line if len(first_line) <= limit else f"{first_line[:limit]}..."

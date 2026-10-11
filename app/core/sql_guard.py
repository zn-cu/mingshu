"""SQL 安全护栏。

LLM 生成的 SQL 会被直接发到数仓执行，提示词里写的“只能用于查询”不是控制手段，
所以这里做代码级兜底：

1. 只允许**单条**语句（禁止 `;` 拼接第二条）；
2. 只允许 `SELECT` / `WITH` 开头；
3. 禁止 DML / DDL / 权限 / 文件读写 / 管理类关键字；
4. 禁止 `FOR UPDATE`、`LOCK IN SHARE MODE` 这类加锁读；
5. 给结果行数加硬上限（在 SQL 外层补 LIMIT），避免一条语句把内存和网络打满。

扫描前会先把注释、字符串常量、反引号标识符替换掉，否则
`where status = 'deleted'` 或列名 `` `set` `` 会被误判成危险关键字。

真正的第一道防线仍然是**只读数据库账号**（见 README 的部署说明）；
这里是应用层兜底，两者不互相替代。
"""

from __future__ import annotations

import re

__all__ = [
    "UnsafeSQLError",
    "assert_read_only",
    "apply_row_limit",
    "assert_safe_identifier",
]


class UnsafeSQLError(ValueError):
    """SQL 未通过安全校验。"""


# 注释（块注释 / -- / #）、字符串常量、反引号标识符
_COMMENT = re.compile(r"/\*.*?\*/|--[^\n]*|#[^\n]*", re.S)
_STRING = re.compile(r"'(?:[^'\\]|\\.|'')*'|\"(?:[^\"\\]|\\.|\"\")*\"", re.S)
_IDENTIFIER = re.compile(r"`[^`]*`")

# 允许的起始关键字
_ALLOWED_HEAD = ("select", "with")

# 危险关键字（按单词边界匹配；'_' 属于 \w，因此 set_code / sleep_hours 不会命中）
#
# 只放“出现在 SELECT 中间也能造成破坏”的词：写操作、DDL、文件读写、锁与资源消耗。
# BEGIN / COMMIT / SET / LOCK TABLES 这类整句语句已经被“首关键字 + 单语句”两条规则挡住，
# 不列进来以免和正常列名冲突。
_FORBIDDEN_KEYWORDS = (
    # 写入
    "insert", "update", "delete", "replace", "upsert", "merge",
    # DDL
    "create", "drop", "alter", "truncate", "rename",
    # 权限
    "grant", "revoke",
    # 文件 / 导入导出
    "outfile", "dumpfile", "infile", "load_file", "load_data", "load",
    # 锁与阻塞
    "get_lock", "release_lock", "for_update",
    # 资源消耗 / 管理
    "sleep", "benchmark", "shutdown", "kill", "flush", "purge",
    "install", "uninstall", "handler", "prepare", "execute", "deallocate", "xa", "call", "do",
)

# 加锁读（普通单词边界匹配会漏掉中间的空格组合）
_LOCKING_READ = re.compile(r"\bfor\s+update\b|\block\s+in\s+share\s+mode\b", re.I)

# 结尾的分号（允许，执行前去掉）
_TRAILING_SEMICOLON = re.compile(r";\s*$")

# 是否已经带 LIMIT（用于决定是追加还是外套一层）
_HAS_LIMIT = re.compile(r"\blimit\b", re.I)

_LIMIT_ALIAS = "da_row_limit"


def _mask(sql: str) -> str:
    """把注释 / 字符串 / 反引号标识符替换成占位符，只留下可判定的结构。"""
    masked = _COMMENT.sub(" ", sql)
    masked = _STRING.sub("''", masked)
    masked = _IDENTIFIER.sub("id", masked)
    return masked


def assert_read_only(sql: str) -> str:
    """校验 SQL 是单条只读查询；通过则返回去掉结尾分号后的原文。

    不通过时抛 :class:`UnsafeSQLError`，消息可直接展示给用户。
    """
    if not sql or not sql.strip():
        raise UnsafeSQLError("生成的 SQL 为空")

    text = _TRAILING_SEMICOLON.sub("", sql.strip()).strip()
    masked = _mask(text)

    # 1. 单语句：去掉结尾分号后，中间不允许再出现分号
    if ";" in masked:
        raise UnsafeSQLError("只允许执行单条 SQL 语句，检测到语句分隔符 ;")

    # 2. 首关键字
    head_source = masked.lstrip("( \t\r\n")
    head_match = re.match(r"[A-Za-z_]+", head_source)
    head = head_match.group(0).lower() if head_match else ""
    if head not in _ALLOWED_HEAD:
        raise UnsafeSQLError(
            f"只允许执行只读查询（SELECT / WITH），实际以 “{head or '?'}” 开头"
        )

    # 3. 危险关键字
    lowered = masked.lower()
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            raise UnsafeSQLError(f"SQL 中禁止出现关键字 {keyword.upper()}")

    # 4. 加锁读（会持有行锁，等价于写事务）
    if _LOCKING_READ.search(lowered):
        raise UnsafeSQLError("禁止使用 FOR UPDATE / LOCK IN SHARE MODE 这类加锁读")

    return text


def apply_row_limit(sql: str, limit: int) -> str:
    """给 SQL 加行数硬上限，多取一行用于判断是否被截断。

    没有 LIMIT 时直接追加（保留原有 ORDER BY 语义）；
    已有 LIMIT 时外套一层子查询，保证总量仍然受限。
    """
    if limit <= 0:
        return sql

    text = _TRAILING_SEMICOLON.sub("", sql.strip()).strip()
    fetch = limit + 1

    if not _HAS_LIMIT.search(_mask(text)):
        return f"{text}\nLIMIT {fetch}"

    return f"SELECT * FROM (\n{text}\n) AS {_LIMIT_ALIAS}\nLIMIT {fetch}"


_IDENTIFIER_OK = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")


def assert_safe_identifier(name: str, *, what: str = "标识符") -> str:
    """校验表名 / 字段名可以安全地拼进 SQL（这些名字来自配置文件，不是用户输入）。

    只接受 MySQL 未加引号的常规标识符；带空格、分号、反引号或非 ASCII 的名字会被拒绝，
    避免把它们拼进语句后产生注入或语法错误。
    """
    if not isinstance(name, str) or not _IDENTIFIER_OK.fullmatch(name):
        raise UnsafeSQLError(
            f"{what} “{name}” 不是合法的 SQL 标识符（只允许字母、数字、下划线、$，且不以数字开头）"
        )
    return name

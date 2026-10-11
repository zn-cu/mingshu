"""SQL 安全护栏（app/core/sql_guard.py）。

**本文件只测「数据库权限拦不住」和「容易被后人改坏」的部分。**

数仓用的是只读账号（实测权限：`USAGE` + `SELECT ON dw.*`），所以
DELETE / UPDATE / INSERT / TRUNCATE / DROP / CREATE / GRANT / CALL / INTO OUTFILE
这类语句由数据库直接拒绝（实测 errno 1142 / 1227 / 1370 / 1045，账号挡住了），
在这里重复测没有意义，故已删除。留下的是三类：

1. **只读账号拦不住的**（护栏是唯一防线，实测 `da_readonly` 均允许执行）：
   - `LOCK IN SHARE MODE`：只需 SELECT 权限，会对真实行加共享锁，可能卡住 ETL；
   - `GET_LOCK()`：命名锁，可阻塞其它取同名锁的会话；
   - `SET SESSION max_execution_time = ...`：能改掉本次连接的超时设置，
     而连接是池化复用的，会影响后续查询；
   - `SLEEP()`：账号允许，虽然 MAX_EXECUTION_TIME 最终会打断它（实测 1 秒设置下
     1.0 秒中断），但护栏能让它**立即**失败而不是白占 30 秒工作线程。
2. **不能误杀正常的 SQL**：关键字出现在字符串常量或反引号标识符里
   （`where status = 'deleted'`、列名 `` `set` ``、`sleep_hours` 等）、CTE、
   带中文常量的真实业务 JOIN —— 护栏要先屏蔽注释/字符串/反引号再扫描，
   这段逻辑最容易被后人「顺手改坏」，所以正反两面都要有用例。
3. **多语句注入**：`select 1; drop table t` 与带注释绕过的变体。

另外保留两项数据库不会替我们保证的能力：结果行数上限、标识符校验
（`dw_mysql_repository` 拼表名/字段名时用它，这类位置无法用参数化占位符）。

本文件的用例都做过**变异测试**校验：把护栏里对应的判断逐条改坏，每条改动都至少有
一条用例失败（否则说明该用例是摆设，应当删除）。
"""

import pytest

from app.core.sql_guard import (
    UnsafeSQLError,
    apply_row_limit,
    assert_read_only,
    assert_safe_identifier,
)

# 只读账号实测允许执行的危险语句 —— 护栏是唯一防线
UNSAFE_SQL = [
    pytest.param("select * from fact_order lock in share mode", id="lock-in-share-mode"),
    pytest.param("select get_lock('x', 10)", id="named-lock"),
    pytest.param("set @a = 1", id="session-variable"),
    pytest.param("set session max_execution_time = 99999999", id="disable-timeout"),
    pytest.param("select sleep(100)", id="sleep"),
    pytest.param("explain select * from fact_order", id="explain-not-allowed"),
    pytest.param("select 1; drop table fact_order", id="multi-statement"),
    pytest.param("select 1; select 2", id="multi-statement-two-selects"),
    pytest.param("select 1 ; -- x\n delete from t", id="multi-statement-comment"),
    pytest.param("", id="empty"),
]

# 必须放行，否则会误杀正常业务查询
SAFE_SQL = [
    pytest.param(
        "SELECT SUM(o.order_amount) AS total FROM fact_order o "
        "JOIN dim_region r ON o.region_id = r.region_id WHERE r.region_name = '华北'",
        id="real-business-sql",
    ),
    # 下面三条分别打中掩码的三个规则：字符串常量、注释、反引号标识符。
    # 破坏 _mask 里任何一条，它们都会失败（已用变异测试验证）。
    pytest.param("select * from t where action = 'delete'", id="keyword-in-string"),
    pytest.param("select * from t -- drop temp table", id="keyword-in-comment"),
    pytest.param("select `insert`, `update` from t", id="keyword-in-backtick-identifier"),
    # 列名里带危险词但不构成独立单词，必须放行（真实表里很常见）
    pytest.param(
        "select order_amount, set_code, sleep_hours, update_time, delete_flag from fact_order",
        id="keyword-prefixed-columns",
    ),
    pytest.param("select * from t where note = 'it''s ok'", id="escaped-quote"),
    pytest.param("with t as (select 1 as a) select * from t", id="cte"),
    pytest.param("select * from fact_order limit 10, 20", id="limit-offset"),
]


@pytest.mark.parametrize("sql", UNSAFE_SQL)
def test_rejects_unsafe_sql(sql):
    with pytest.raises(UnsafeSQLError):
        assert_read_only(sql)


@pytest.mark.parametrize("sql", SAFE_SQL)
def test_allows_read_only_sql(sql):
    assert assert_read_only(sql)


def test_trailing_semicolon_is_stripped():
    assert assert_read_only("select 1;") == "select 1"


def test_apply_row_limit_appends_when_no_limit():
    assert apply_row_limit("select * from t", 1000) == "select * from t\nLIMIT 1001"


def test_apply_row_limit_wraps_when_limit_exists():
    limited = apply_row_limit("select * from t limit 5", 1000)
    assert limited.startswith("SELECT * FROM (")
    assert "LIMIT 1001" in limited
    assert "select * from t limit 5" in limited


def test_apply_row_limit_zero_means_no_limit():
    assert apply_row_limit("select 1", 0) == "select 1"


def test_safe_identifier_passes():
    assert assert_safe_identifier("fact_order") == "fact_order"


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("fact_order; drop table x", id="injection"),
        pytest.param("fact order", id="whitespace"),
        pytest.param(None, id="none"),
    ],
)
def test_unsafe_identifier_rejected(name):
    with pytest.raises(UnsafeSQLError):
        assert_safe_identifier(name)

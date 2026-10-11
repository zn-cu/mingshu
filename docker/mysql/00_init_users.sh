#!/bin/bash
# 初始化数据库与账号授权。
#
# 账号与密码全部来自环境变量（见 docker/.env.example），因此仓库里不出现任何真实凭据。
# 本脚本按文件名排序最先执行，之后才执行 dw.sql / meta.sql 里的建表与数据。
#
# 注意：/docker-entrypoint-initdb.d 下的脚本只在「数据卷为空」时执行一次；
# 已有数据卷的环境需要手动执行同样的语句（或重建数据卷）。

: "${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD 未设置，请在 docker/.env 中配置}"
: "${MYSQL_USER:?MYSQL_USER 未设置，请在 docker/.env 中配置}"
: "${MYSQL_PASSWORD:?MYSQL_PASSWORD 未设置，请在 docker/.env 中配置}"
: "${DA_READONLY_USER:?DA_READONLY_USER 未设置，请在 docker/.env 中配置}"
: "${DA_READONLY_PASSWORD:?DA_READONLY_PASSWORD 未设置，请在 docker/.env 中配置}"

# 用 MYSQL_PWD 传密码，避免命令行参数带来的告警
MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql --protocol=socket -uroot <<SQL || exit 1
CREATE DATABASE IF NOT EXISTS meta CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
CREATE DATABASE IF NOT EXISTS dw   CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

-- 应用主账号：元数据库需要写权限（元知识构建脚本要写表 / 字段 / 指标）
GRANT ALL PRIVILEGES ON meta.* TO '${MYSQL_USER}'@'%';
GRANT ALL PRIVILEGES ON dw.*   TO '${MYSQL_USER}'@'%';

-- 数仓只读账号：LLM 生成的 SQL 由它执行，数据库层面就写不进去
CREATE USER IF NOT EXISTS '${DA_READONLY_USER}'@'%' IDENTIFIED BY '${DA_READONLY_PASSWORD}';
GRANT SELECT ON dw.* TO '${DA_READONLY_USER}'@'%';

FLUSH PRIVILEGES;
SQL

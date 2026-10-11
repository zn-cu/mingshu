# 明数（MingShu）· LucidData

**用自然语言查询数据仓库的智能体（NL2SQL Agent）。**

业务同学想问「统计华北地区的销售总额」，不用写 SQL、也不用等数据同学排期：
在页面上提问，系统自动理解问题、找到相关的表 / 字段 / 指标，生成 SQL 并执行，
把查询结果和**每一步的执行进度**实时返回。生成的 SQL 要过安全护栏与语法校验，
失败时自动校正后重试。

项目由两部分组成：

- **元数据知识库（离线构建）**：把数仓的表、字段、指标、字段取值同步进 MySQL，
  并建立两份检索索引 —— Qdrant 存字段 / 指标的向量（语义召回），
  Elasticsearch 存维度取值的全文索引（把「华北」这类说法匹配到库里的真实取值）。
- **问数智能体（在线查询）**：LangGraph 编排的 12 节点流程 —— 关键词抽取 → 多路召回 →
  合并过滤 → 生成 SQL → 校验 →（必要时）自动校正 → 执行。

```
conf/meta_config.yaml ──► 构建脚本 ──┬──► MySQL(meta)    表 / 字段 / 指标
                                    ├──► Qdrant         字段与指标向量
                                    └──► Elasticsearch  维度取值全文索引
                                              │
用户问题 ──► 12 节点工作流（多路召回 → 生成 SQL → 校验 / 校正 → 执行）──► SSE 流式返回
```

## 部署流程

前置要求：

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | 最新 | Python 依赖与虚拟环境（缺 Python 3.12 会自动装） |
| Docker + Docker Compose | — | 起 MySQL / Elasticsearch / Qdrant / TEI |
| Node.js | ≥ 20.19 | 前端构建（Vite 7 要求） |
| 大模型 API Key | — | DashScope 或任意 OpenAI 兼容服务 |
| 磁盘 | 约 5 GB | 容器镜像 + 1.2 GB 向量模型 |

- [ ] **1. 克隆仓库**

    ```bash
    git clone https://github.com/zn-cu/mingshu.git && cd mingshu
    ```

- [ ] **2. 填依赖服务的密码** —— `docker/.env`（不提交）

    ```bash
    cd docker && cp .env.example .env    # Windows: copy .env.example .env
    ```

- [ ] **3. 下载向量模型权重**（约 1.2 GB，不随仓库分发）到 `docker/embedding/bge-large-zh-v1.5/`

    ```bash
    hf download BAAI/bge-large-zh-v1.5 --local-dir ./embedding/bge-large-zh-v1.5
    ```

    国内网络可用 `modelscope download --model BAAI/bge-large-zh-v1.5 --local_dir <同上>`，
    或设 `HF_ENDPOINT=https://hf-mirror.com`；也可以删掉 compose 里该服务的 `volumes`，让 TEI 自行下载。

- [ ] **4. 启动依赖服务**（MySQL / Elasticsearch / Kibana / Qdrant / 向量服务）

    ```bash
    docker compose up -d && docker compose ps     # 五个服务都应是 running
    ```

    首次启动会执行初始化脚本：建库建号（含数仓只读账号）、写入数仓示例数据与元数据表结构。

- [ ] **5. 填本机密钥** —— 新建 `conf/app_config.local.yaml`

    ```yaml
    db_meta: {user: <可写账号>, password: <密码>}
    db_dw:   {user: da_readonly, password: <密码>}   # 必须是只读账号
    llm:     {api_key: sk-xxx}
    ```

    **不要改仓库里的 `conf/app_config.yaml`**——那是要提交的脱敏版，改了会被 git 跟踪、还可能误提交真实密钥。
    这里的账号密码要与 `docker/.env` 一致；也可以改用环境变量（配置里已写成 `${oc.env:变量名,默认值}`）。

- [ ] **6. 构建元数据知识库** —— 把表 / 字段 / 指标写进 MySQL，并建立 Qdrant 向量索引与 ES 全文索引

    ```bash
    uv run python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml
    ```

    ⚠️ **这步不能省**：跳过的症状是「服务都能起、页面能打开，但一问就召回不到表 / 字段」。
    漏了的话 `GET /ready` 会直接提示「集合 xxx 不存在，请先执行元知识构建脚本」。脚本幂等，可反复执行。

- [ ] **7. 启动后端**

    ```bash
    uv sync                   # 可选：uv run 也会自动同步依赖
    uv run fastapi dev        # http://127.0.0.1:8000
    ```

- [ ] **8. 启动前端**（另开一个终端）

    ```bash
    cd frontend && npm install && npm run dev   # http://localhost:5173
    ```

- [ ] **9. 验证**

    ```bash
    curl http://127.0.0.1:8000/health   # {"status":"ok",...}
    curl http://127.0.0.1:8000/ready    # 六个依赖项全部 ok=true（任一项不通过返回 503）
    ```

    然后打开 <http://localhost:5173> 提问「统计华北地区的销售总额」：左侧 11 个步骤依次点亮，右侧表格显示销售总额。

后端接口：`POST /api/query`（SSE，实时推送进度与结果）、`GET /health`（存活）、`GET /ready`（就绪）。

依赖服务默认端口：MySQL `3306`、Elasticsearch `9200`、Kibana `5601`、Qdrant `6333`、向量服务 `8081`。

## 项目结构

```
mingshu/
├── app/
│   ├── agent/          # 智能体：graph（图定义）、state、nodes（12 个节点）、step（节点装饰器）
│   ├── api/            # 接口：routers（查询 / 健康检查）、schemas、dependencies（依赖注入 + 鉴权）、lifespan
│   ├── clients/        # 外部服务客户端：mysql / qdrant / es / embedding
│   ├── conf/           # 配置类（OmegaConf 结构化 schema）
│   ├── core/           # 基础设施：日志、上下文、SQL 护栏、错误分类、启动自检
│   ├── entities/       # 业务实体        models/  # ORM 实体（meta 库四张表）
│   ├── prompt/         # 提示词加载
│   ├── repositories/   # 数据访问：mysql(meta/dw)、qdrant、es
│   ├── scripts/        # 脚本：build_meta_knowledge（元数据知识库构建）
│   └── services/       # 业务逻辑：meta_knowledge_service、query_service
├── conf/               # 配置：app_config.yaml（脱敏版，可提交）/ meta_config.yaml（元数据定义）
├── docker/             # 依赖服务编排、初始化 SQL、ES 镜像（含 IK 分词）
├── frontend/           # 前端：Vue 3 + Vite 单页应用（零第三方运行时依赖）
├── prompts/            # 提示词模板（7 个）
├── checks/             # 检查：单元检查 + 集成检查（`uv run pytest`，集成检查默认跳过）
└── .github/workflows/  # CI（ruff + pytest）
```

## 注意事项

1. **数仓必须用只读账号**。LLM 生成的 SQL 由它执行，数据库层面就写不进去；
   代码里还有一层 SQL 护栏（只允许单条 `SELECT` / `WITH`，禁 DML / DDL / 加锁读）与
   行数、超时上限兜底。建号语句：

   ```sql
   CREATE USER 'da_readonly'@'%' IDENTIFIED BY '<password>';
   GRANT SELECT ON dw.* TO 'da_readonly'@'%';
   ```

2. **密钥不要写进 `conf/app_config.yaml`**（它会被提交）。真实凭据放
   `conf/app_config.local.yaml`（已被 `.gitignore` 排除），或走环境变量
   （配置里已写成 `${oc.env:变量名,默认值}`）。加载顺序：基础配置 → local 覆盖文件。

3. **向量模型权重不进仓库**（约 1.2 GB），需要自己下载到 `docker/embedding/bge-large-zh-v1.5/`：

   ```bash
   hf download BAAI/bge-large-zh-v1.5 --local-dir ./docker/embedding/bge-large-zh-v1.5
   ```
   国内网络可用 `modelscope download --model BAAI/bge-large-zh-v1.5 --local_dir <同上>`
   或 `HF_ENDPOINT=https://hf-mirror.com`；也可以删掉 compose 里该服务的 `volumes` 让 TEI 自行下载。

4. **数据卷**：compose 用普通命名卷（`mingshu_mysql_data` 等）。若要从旧环境迁移、
   复用已有数据卷，把 `docker-compose.yaml` 里对应卷改成 `external: true` 加实际卷名，
   否则会新建空卷（**看不到原有数据**）。

5. **接自己的基础设施**（不用 `docker/` 编排）时，按顺序执行：
   `docker/mysql/00_init_users.sh`（建库建号）→ `dw.sql`（数仓表与示例数据）→
   `meta.sql`（元数据四张表）。

6. **改元数据**：编辑 `conf/meta_config.yaml`（表 / 字段 / 指标 / 别名 / 取值是否建全文索引），
   重跑构建脚本即可。脚本幂等 —— 先删本次同步范围内的旧记录再写入，
   Qdrant 点 id 与 ES 文档 `_id` 都由内容派生，重复执行不会产生重复数据。

7. **当前限制**：工作流没有 checkpointer，每次提问都是独立执行、不继承上下文；
   界面暂不展示生成的 SQL（SQL 只写日志，后端未推 `sql` 事件）。

8. **前端依赖下载慢**时可换镜像：`npm config set registry https://registry.npmmirror.com`。

9. **超时与校正的预算**：单次模型调用 45 秒、失败重试 2 次（`llm.timeout_seconds` / `llm.max_retries`，
   超时也会重试），最坏约 135 秒，仍在一次问答的整体上限 180 秒（`query.request_timeout_seconds`）之内。
   SQL 校验不过会自动让模型校正，默认 2 次（`agent.max_sql_corrections`），**校正后会重新校验**；
   次数用完仍不通过就直接报错，不会把没通过校验的 SQL 发到数仓。

10. **接口鉴权与跨域（都可选）**：`api.api_key` 留空时不校验（本地开发零配置）；填了之后
    `POST /api/query` 必须带请求头 `X-API-Key`，前端用 `VITE_API_KEY` 对齐（见
    [`frontend/.env.example`](frontend/.env.example)）；`/health` 与 `/ready` 始终不鉴权，探针不受影响。
    前端构建产物部署到其它域名/端口时，把来源加进 `api.cors_origins`（留空则完全不启用 CORS）。
    另外 `/ready` 里「向量服务」那项默认缓存 60 秒（`api.ready_cache_seconds`），
    避免健康检查把向量服务打满。

11. **启动自检会检查模型配置**：`/ready`（以及启动日志）里有一项 `llm`，判断
    `llm.api_key` / `model_name` / `base_url` 是否都配了，漏配时 `/ready` 返回 503 并直接给出修复方式，
    不用等用户提问才发现。它**只判断有没有配，不校验密钥是否有效**（那需要真的调一次模型，
    健康检查不该为此花钱；密钥写错会在第一次提问时报出明确错误）。

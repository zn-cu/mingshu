import asyncio

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, async_sessionmaker

from app.conf.app_config import DBConfig, app_config


class MySQLClientManager:
    def __init__(self, config: DBConfig):
        self.engine: AsyncEngine | None = None
        self.session_factory = None
        self.config = config

    def _get_url(self) -> URL:
        """用 URL.create 构造 DSN。

        原来是手拼字符串 f"mysql+asyncmy://{user}:{password}@{host}..."，
        一旦用户名或密码里出现 @ : / ? # 这类字符，URL 就会被解析错
        （现在数仓用的是只读账号，密码可能带特殊字符，所以这里必须正规化）。
        """
        return URL.create(
            drivername="mysql+asyncmy",
            username=self.config.user,
            password=self.config.password,
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            query={"charset": "utf8mb4"},
        )

    def init(self):
        self.engine = create_async_engine(self._get_url(), pool_size=10, pool_pre_ping=True)
        self.session_factory= async_sessionmaker(self.engine, autoflush=True, expire_on_commit=False)

    async def close(self):
        if self.engine is not None:
            await self.engine.dispose()


meta_mysql_client_manager = MySQLClientManager(app_config.db_meta)
dw_mysql_client_manager = MySQLClientManager(app_config.db_dw)

if __name__ == '__main__':
    dw_mysql_client_manager.init()


    async def test():
        async with dw_mysql_client_manager.session_factory() as session:
            sql = "select * from fact_order limit 10"
            result = await session.execute(text(sql))

            rows = result.mappings().fetchall()

            print(type(rows))
            print(type(rows[0]))
            print(rows[0]['order_id'])


    asyncio.run(test())

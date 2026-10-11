"""测试环境准备。

配置直接读仓库里提交的脱敏版 `conf/app_config.yaml`（不含真实凭据），
所以 CI 与新克隆的环境都能直接跑单元测试 —— 各客户端都是懒连接，不会真的去连。
如果本机存在 `conf/app_config.local.yaml`，它会作为覆盖被一起加载（单元测试同样不受影响）。
"""

import pytest


@pytest.fixture
def anyio_backend():
    """让 anyio 的 pytest 插件只跑 asyncio 后端。"""
    return "asyncio"

"""节点执行样板。

每个节点都要写「发 running 事件 → 干业务 → 发 success/error 事件 → 记异常日志」，
12 个节点重复了 12 遍。这里用装饰器统一处理，节点函数只保留业务逻辑：

    @step("运行SQL")
    async def run_sql(state, runtime):
        ...
        return {"sql": ...}   # 返回要合并进 state 的字典

约定：函数正常返回 => 这一步记为 success；抛异常 => 记为 error 并记完整堆栈后继续上抛。
"""

from functools import wraps

from app.core.log import logger


def step(name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(state, runtime):
            writer = runtime.stream_writer
            writer({"type": "progress", "step": name, "status": "running"})
            try:
                result = await func(state, runtime)
            except Exception as e:
                logger.exception(f"{name} failed: {e}")
                writer({"type": "progress", "step": name, "status": "error"})
                raise
            writer({"type": "progress", "step": name, "status": "success"})
            return result

        return wrapper

    return decorator

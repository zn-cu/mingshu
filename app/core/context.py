from contextvars import ContextVar

# 请求上下文里的 request_id，由 main.py 的中间件写入，日志格式里会带上。
# 不在请求上下文时（启动阶段、离线脚本）用 n/a 占位，避免日志里出现无意义的编号。
request_id_context_var: ContextVar[str] = ContextVar('request_id', default='n/a')

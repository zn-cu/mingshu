from langchain.chat_models import init_chat_model

from app.conf.app_config import app_config

# 单次调用必须有超时：否则模型侧挂住时，请求会一直悬着（SDK 默认超时是 600 秒）
#
# api_key 为空时给个占位值：openai SDK 在**构造客户端**时就要求 key 非空，
# 而新克隆的仓库里 api_key 是空的（脱敏配置 + 还没配密钥），
# 那样连 import 都会失败 —— 应用起不来、测试也收集不了。
# 用占位值让应用能启动，真正调用模型时才会因凭证无效报错（错误信息也清楚得多）。
llm = init_chat_model(model=app_config.llm.model_name,
                      model_provider="openai",
                      base_url=app_config.llm.base_url,
                      api_key=app_config.llm.api_key or "EMPTY",
                      temperature=0,
                      timeout=app_config.llm.timeout_seconds,
                      max_retries=app_config.llm.max_retries)

if __name__ == '__main__':
    print(llm.invoke("你好").content)

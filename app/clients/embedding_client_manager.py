import asyncio

from langchain_openai import OpenAIEmbeddings

from app.conf.app_config import EmbeddingConfig, app_config


class EmbeddingClientManager:
    def __init__(self, config: EmbeddingConfig):
        self.client: OpenAIEmbeddings | None = None
        self.config = config

    def _get_url(self):
        return f"http://{self.config.host}:{self.config.port}/v1"

    def init(self):
        self.client = OpenAIEmbeddings(model=self.config.model,
                                       base_url=self._get_url(),
                                       api_key="EMPTY",
                                       check_embedding_ctx_length=False,
                                       # 必须显式设超时：不设就是 SDK 默认的 600 秒
                                       request_timeout=self.config.timeout_seconds,
                                       max_retries=1)

embedding_client_manager = EmbeddingClientManager(app_config.embedding)


if __name__ == '__main__':
    embedding_client_manager.init()
    client = embedding_client_manager.client

    async def test():
        text = "What is deep learning?"
        query_result = await client.aembed_query(text)
        print(query_result[:3])

    asyncio.run(test())
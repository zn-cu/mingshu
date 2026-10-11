from pydantic import BaseModel, Field, field_validator


class QuerySchema(BaseModel):
    # 限制长度：原来没有任何约束，空串或几万字的输入会直接送进模型
    query: str = Field(min_length=1, max_length=2000, description="用户的自然语言问题")

    @field_validator("query")
    @classmethod
    def _strip_and_check(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query 不能为空白")
        return value

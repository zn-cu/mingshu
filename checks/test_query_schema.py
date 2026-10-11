"""请求体校验（app/api/schemas/query_schema.py）。"""

import pytest
from pydantic import ValidationError

from app.api.schemas.query_schema import QuerySchema


def test_accepts_normal_question():
    assert QuerySchema(query="统计华北地区的销售总额").query == "统计华北地区的销售总额"


def test_strips_surrounding_whitespace():
    assert QuerySchema(query="  统计销售额  ").query == "统计销售额"


def test_accepts_max_length_boundary():
    assert len(QuerySchema(query="x" * 2000).query) == 2000


@pytest.mark.parametrize("bad", ["", "   ", "\n\t ", "x" * 2001])
def test_rejects_empty_blank_or_too_long(bad):
    with pytest.raises(ValidationError):
        QuerySchema(query=bad)

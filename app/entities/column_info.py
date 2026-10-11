from dataclasses import dataclass
from typing import Any

from app.entities.normalize import as_list


@dataclass
class ColumnInfo:
    id: str
    name: str
    type: str
    role: str
    examples: list[Any]
    description: str
    alias: list[str]
    table_id: str

    def __post_init__(self):
        # examples / alias 在库里是可空 JSON，取出来可能是 None 或标量，统一成 list
        self.examples = as_list(self.examples)
        self.alias = as_list(self.alias)

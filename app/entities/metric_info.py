from dataclasses import dataclass

from app.entities.normalize import as_list


@dataclass
class MetricInfo:
    id: str
    name: str
    description: str
    relevant_columns: list[str]
    alias: list[str]

    def __post_init__(self):
        # relevant_columns / alias 在库里是可空 JSON，统一成 list
        self.relevant_columns = as_list(self.relevant_columns)
        self.alias = as_list(self.alias)

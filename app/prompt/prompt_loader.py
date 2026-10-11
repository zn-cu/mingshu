from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """读取提示词模板。

    加了缓存：原来每次节点执行都读一次磁盘（每个请求 5~6 次文件 IO），
    提示词在进程生命周期内不会变，缓存即可。
    """
    prompt_path = Path(__file__).parents[2] / 'prompts' / f"{name}.prompt"
    return prompt_path.read_text(encoding="utf-8")

import jieba.analyse
from langgraph.runtime import Runtime

from app.agent.context import AgentContext
from app.agent.state import AgentState
from app.agent.step import step
from app.core.log import logger


@step("抽取关键词")
async def extract_keywords(state: AgentState, runtime: Runtime[AgentContext]):
    query = state["query"]

    allow_pos = (
        "n",  # 名词: 数据、服务器、表格
        "nr",  # 人名: 张三、李四
        "ns",  # 地名: 北京、上海
        "nt",  # 机构团体名: 政府、学校、某公司
        "nz",  # 其他专有名词: Unicode、哈希算法、诺贝尔奖
        "v",  # 动词: 运行、开发
        "vn",  # 名动词: 工作、研究
        "a",  # 形容词: 美丽、快速
        "an",  # 名形词: 难度、合法性、复杂度
        "eng",  # 英文
        "i",  # 成语
        "l",  # 常用固定短语
    )

    keywords = jieba.analyse.extract_tags(query, allowPOS=allow_pos)

    # 去重且保持顺序：原来用 set()，同样的提问每次关键词顺序都不同，
    # 会让召回顺序、最终 SQL 都不可复现
    keywords = list(dict.fromkeys(keywords + [query]))

    logger.info(f"抽取关键词成功: {keywords}")
    return {"keywords": keywords}

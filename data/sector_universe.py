"""股票板块 / 行业 / 题材 标签定义

用于在回测或实时环境下，为股票附加行业板块、概念题材等标签，
后续可以基于这些标签计算板块级加权指标（涨跌、成交量、强度等）。

说明：
- 这里只定义了一小部分与示例/Mock 数据重合的股票，用于演示；
- 真正接入实盘时，可以替换为从数据库或数据源动态加载的映射。
"""

from typing import Dict, List


# 简单的行业 + 题材映射示例
# key: symbol, value: dict with 'industry' and 'themes' (list)
SYMBOL_TAGS: Dict[str, Dict[str, object]] = {
    # 新能源 / 电池
    "300750.SZ": {
        "industry": "电力设备",
        "themes": ["新能源", "锂电池", "储能"],
    },
    # 银行
    "600036.SH": {
        "industry": "银行",
        "themes": ["大金融"],
    },
    # 白酒
    "000568.SZ": {
        "industry": "白酒",
        "themes": ["消费", "高端白酒"],
    },
    # 家电
    "000333.SZ": {
        "industry": "家电",
        "themes": ["消费电子", "白电"],
    },
    # 贵州茅台
    "600519.SH": {
        "industry": "白酒",
        "themes": ["消费", "白酒", "高端白酒"]
    },
    # 比亚迪
    "002594.SZ": {
        "industry": "汽车",
        "themes": ["新能源", "新能源汽车", "整车"],
    },
}


def get_symbol_tags(symbol: str) -> Dict[str, object]:
    """获取单只股票的行业/题材标签。

    返回结构：{"industry": str or None, "themes": List[str]}。
    未配置的股票返回空标签。
    """
    info = SYMBOL_TAGS.get(symbol)
    if not info:
        return {"industry": None, "themes": []}

    industry = info.get("industry")
    themes = list(info.get("themes") or [])
    return {"industry": industry, "themes": themes}


def get_all_industries() -> List[str]:
    """返回所有已配置的行业名称列表。"""
    inds = {v.get("industry") for v in SYMBOL_TAGS.values() if v.get("industry")}
    return sorted(inds)


def get_all_themes() -> List[str]:
    """返回所有已配置的题材名称列表。"""
    themes = set()
    for v in SYMBOL_TAGS.values():
        for t in v.get("themes") or []:
            themes.add(t)
    return sorted(themes)

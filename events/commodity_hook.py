"""
商品事件检测钩子 — 接入事件流水线
==================================
在 NLP Pipeline 之后、EventBus 发布之前, 检测商品突发事件。
检测到商品信号时自动标记 FinancialEvent.tags, 并写入 PG 信号表。

接入方式 (在 scheduler.py 或 adapter.py 中):
    from astock_engine.events.commodity_hook import CommodityEventHook
    hook = CommodityEventHook()

    # 方式1: 对单个事件做检测
    event = hook.process(event)

    # 方式2: 批量检测
    events = hook.process_batch(events)

PG 输出: alpha.commodity_event_signals
"""

import sys, os, json, re, logging
from datetime import datetime
from typing import List, Optional, Dict

logger = logging.getLogger("commodity_hook")

# 运行时注入项目路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── 事件模式库 (与 commodity_event_detector.py 同步) ──

EVENT_PATTERNS = [
    (r"(矿|油田|气田).{0,8}(事故|崩塌|透水|爆炸|火灾|停产|停工|关闭)",
     lambda m: ("supply_disruption", "事故停产", 1.0)),
    (r"(地震|洪水|暴雨|台风|泥石流|暴雪).{0,10}(矿|油田|厂区|产区|主产区)",
     lambda m: ("supply_disruption", "自然灾害", 0.8)),
    (r"(环保|能耗|碳达峰|限产|错峰|压减|去产能|淘汰落后).{0,15}(产能|产量|开工|生产)",
     lambda m: ("policy_restriction", "政策限产", 0.7)),
    (r"(发改委|工信部|生态环境部|应急管理部).{0,15}(产能|限产|停产|整顿|关停)",
     lambda m: ("policy_restriction", "行政限产", 0.8)),
    (r"(禁止|限制|叫停|暂停).{0,6}(进口|出口|通关|报关)",
     lambda m: ("trade_restriction", "贸易限制", 0.8)),
    (r"(反倾销|反补贴|加征关税|制裁).{0,10}(进口|产品|商品)",
     lambda m: ("trade_restriction", "贸易壁垒", 0.7)),
    (r"(港口|码头|铁路|管道).{0,8}(封闭|中断|停运|拥堵|罢工)",
     lambda m: ("logistics_disruption", "运输中断", 0.8)),
    (r"(国储|收储|抛储|轮储|战略储备).{0,6}(铜|铝|锌|镍|棉花|白糖|橡胶|原油|猪肉)",
     lambda m: ("reserve_operation", "国储操作", 0.9)),
    (r"(检修|大修|停产检修|投产|新产能|装置投产).{0,10}(万吨|产能|装置|PTA|甲醇|纯碱|尿素|乙烯|丙烯)",
     lambda m: ("capacity_event", "装置变动", 0.6)),
    (r"(罢工|劳资|工会).{0,6}(矿|油田|港口)",
     lambda m: ("supply_disruption", "罢工停产", 0.7)),
    (r"(疫情|封控|静默).{0,12}(产区|工厂|矿|码头|运输)",
     lambda m: ("supply_disruption", "疫情封控", 0.6)),
]

COMMODITY_KEYWORDS = {
    "锂": ["lithium_carbonate", "lithium"], "碳酸锂": ["lithium_carbonate"],
    "铜": ["copper"], "铝": ["aluminum"], "锌": ["zinc"], "铅": ["lead"],
    "镍": ["nickel"], "锡": ["tin"], "黄金": ["gold"], "白银": ["silver"],
    "铁矿石": ["iron_ore"], "螺纹钢": ["rebar"], "热轧": ["hot_rolled_coil"],
    "焦煤": ["coking_coal"], "焦炭": ["coke"], "动力煤": ["thermal_coal"], "煤": ["thermal_coal"],
    "原油": ["crude_oil"], "石油": ["crude_oil"], "天然气": ["natural_gas"],
    "PTA": ["pta"], "乙二醇": ["ethylene_glycol"], "聚丙烯": ["polypropylene"],
    "PVC": ["pvc"], "甲醇": ["methanol"], "纯碱": ["soda_ash"], "烧碱": ["caustic_soda"],
    "尿素": ["urea"], "苯乙烯": ["styrene"], "醋酸": ["acetic_acid"],
    "钛白粉": ["titanium_dioxide"], "磷酸": ["phosphoric_acid"], "硫酸": ["sulfuric_acid"],
    "水泥": ["cement"], "玻璃": ["glass"], "浮法": ["float_glass"],
    "豆粕": ["soybean_meal"], "大豆": ["soybean"], "豆油": ["soybean_oil"],
    "玉米": ["corn"], "棕榈油": ["palm_oil"], "菜油": ["rapeseed_oil"],
    "棉花": ["cotton"], "白糖": ["sugar"], "橡胶": ["rubber"], "纸浆": ["pulp"],
    "生猪": ["live_hog"], "猪": ["live_hog"], "鸡蛋": ["egg"],
    "稀土": ["rare_earth"], "钨": ["tungsten"], "钴": ["cobalt"],
    "工业硅": ["silicon_metal"], "多晶硅": ["polysilicon"],
    "六氟磷酸锂": ["lipf6"], "电解液": ["electrolyte"],
    "锂矿": ["lithium_carbonate", "lithium"],
    "铜矿": ["copper"], "铝矿": ["aluminum"], "铁矿": ["iron_ore"],
}


class CommodityEventHook:
    """商品事件检测钩子 — 接入 NLP Pipeline 后处理"""

    def __init__(self, pg_conn=None):
        self._pg = pg_conn
        self._detection_count = 0

    def detect(self, text: str) -> list:
        """从文本检测商品事件"""
        results = []
        triggered = []
        for pattern, resolver in EVENT_PATTERNS:
            m = re.search(pattern, text)
            if m:
                event_type, event_name, urgency = resolver(m)
                triggered.append((event_type, event_name, urgency))

        if not triggered:
            return []

        commodities = set()
        for kw, pids in COMMODITY_KEYWORDS.items():
            if kw in text:
                for pid in pids:
                    commodities.add(pid)

        if not commodities:
            return []

        event_type, event_name, urgency = max(triggered, key=lambda x: x[2])
        direction = +1 if event_type in (
            "supply_disruption","policy_restriction","trade_restriction",
            "logistics_disruption","reserve_operation") else -1

        for pid in commodities:
            results.append({
                "product_id": pid,
                "event_type": event_type,
                "event_name": event_name,
                "urgency": urgency,
                "direction": direction,
            })
        return results

    def process(self, event: "FinancialEvent") -> "FinancialEvent":
        """处理单个 FinancialEvent, 附加商品信号到 tags"""
        text = f"{event.title} {event.summary}"
        commodity_events = self.detect(text)

        if commodity_events:
            self._detection_count += 1
            # 序列化到 tags (EventBus 兼容)
            event.tags["commodity_event"] = "true"
            event.tags["commodity_count"] = str(len(commodity_events))
            for i, ce in enumerate(commodity_events[:5]):  # 最多5个
                prefix = f"cm_{i}"
                event.tags[f"{prefix}_pid"] = ce["product_id"]
                event.tags[f"{prefix}_type"] = ce["event_type"]
                event.tags[f"{prefix}_name"] = ce["event_name"]
                event.tags[f"{prefix}_dir"] = str(ce["direction"])
                event.tags[f"{prefix}_urgency"] = str(ce["urgency"])

            # 写入 PG
            self._write_signal(event, commodity_events)

            logger.info(f"[CommodityHook] 检测到商品事件: "
                        f"{len(commodity_events)}品种 | {event.title[:60]}")

        return event

    def process_batch(self, events: List["FinancialEvent"]) -> List["FinancialEvent"]:
        """批量处理"""
        return [self.process(e) for e in events]

    def _write_signal(self, event, commodity_events):
        """写入 PG 事件信号表"""
        if not self._pg:
            self._ensure_pg()
        if not self._pg:
            return

        try:
            cur = self._pg.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alpha.commodity_event_signals (
                    id          SERIAL PRIMARY KEY,
                    created_at  TIMESTAMPTZ DEFAULT NOW(),
                    product_id  VARCHAR(64) NOT NULL,
                    event_type  VARCHAR(32),
                    event_name  VARCHAR(64),
                    urgency     DOUBLE PRECISION,
                    direction   INT,
                    title       TEXT,
                    source      VARCHAR(32)
                )
            """)
            for ce in commodity_events:
                cur.execute("""
                    INSERT INTO alpha.commodity_event_signals
                    (product_id, event_type, event_name, urgency, direction, title, source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (ce["product_id"], ce["event_type"], ce["event_name"],
                      ce["urgency"], ce["direction"],
                      event.title[:500], event.source))
            self._pg.commit()
        except Exception as e:
            logger.warning(f"[CommodityHook] PG写入失败: {e}")

    def _ensure_pg(self):
        """延迟初始化 PG 连接"""
        try:
            from tools.db_config import pg_connect
            self._pg = pg_connect()
        except Exception as e:
            logger.warning(f"[CommodityHook] PG连接失败: {e}")

    @property
    def detection_count(self) -> int:
        return self._detection_count


# ── 便捷函数: 一行接入 ──

def create_commodity_hook() -> CommodityEventHook:
    """创建商品事件钩子 (供 scheduler/adapter 调用)"""
    return CommodityEventHook()


# ── 测试 ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    hook = CommodityEventHook()

    texts = [
        "突发! 澳洲锂矿停产, 影响全球供应",
        "发改委要求压减钢铁产能5000万吨",
        "华东港口大雾封港, PTA大量滞留",
    ]
    for t in texts:
        results = hook.detect(t)
        print(f"\n{t}")
        for r in results:
            direction = "利多" if r["direction"] > 0 else "利空"
            print(f"  → {r['product_id']} [{r['event_name']}] {direction} 紧急度={r['urgency']:.0%}")

"""
新闻风控监控系统测试脚本
========================
向 C++ EventBus 发布测试金融事件，验证 EventRiskSubscriber 是否正确响应。

测试场景:
  1. 立案调查 → 封禁标的 + 收紧止损至 5% + 仓位上限降至 2%
  2. ST警示   → 封禁标的 + 仓位上限降至 2%
  3. 政策负面 → 高置信度负面时总敞口降至 80%
  4. 普通新闻 → 不触发风控变更

验证方式:
  - 观察 C++ 侧日志: [EventRisk] 风控参数变更
  - 观察 C++ 侧日志: [EventRisk] 已订阅 news.* 事件
  - blockedSymbols 在下一交易日 evaluateEndOfDay 入口清空
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from event_types import FinancialEvent, FinancialEventType
from publisher import EventPublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("TestNewsMonitor")


def test_investigation_block():
    """测试1: 立案调查 → 封禁开仓 + 收紧风控"""
    logger.info("=" * 60)
    logger.info("测试1: 立案调查事件")
    event = FinancialEvent(
        source="cninfo",
        title="ST柏龙收到证监会立案调查通知书",
        summary="因涉嫌信息披露违法违规，证监会决定对公司立案调查",
        symbols=["002776"],
        sentiment_score=-0.95,
        event_type=FinancialEventType.MATERIAL,
        confidence=0.92,
        tags={"立案调查": "true"},
    )
    publisher = EventPublisher()
    ok = publisher.publish_one(event)
    logger.info(f"  发布结果: {'✓ 成功' if ok else '✗ 失败'}")
    logger.info("  预期: [EventRisk] 风控参数变更 trigger=news.material symbol=002776")
    logger.info("  预期: stopLoss收紧, positionLimit降为2%, 002776加入封禁名单")
    return ok


def test_st_warning():
    """测试2: ST警示 → 封禁开仓 + 降仓位"""
    logger.info("=" * 60)
    logger.info("测试2: ST警示事件")
    event = FinancialEvent(
        source="eastmoney",
        title="ST鹏博被实施退市风险警示",
        summary="因最近一个会计年度经审计的净资产为负值，公司股票将被实施退市风险警示",
        symbols=["600804"],
        sentiment_score=-0.88,
        event_type=FinancialEventType.ALERT,
        confidence=0.90,
        tags={"ST警示": "true"},
    )
    publisher = EventPublisher()
    ok = publisher.publish_one(event)
    logger.info(f"  发布结果: {'✓ 成功' if ok else '✗ 失败'}")
    logger.info("  预期: [EventRisk] 风控参数变更 trigger=news.alert symbol=600804")
    logger.info("  预期: positionLimit降为2%, 600804加入封禁名单")
    return ok


def test_policy_negative():
    """测试3: 高置信度政策负面 → 降总敞口"""
    logger.info("=" * 60)
    logger.info("测试3: 政策负面事件")
    event = FinancialEvent(
        source="cls",
        title="工信部拟出台光伏行业产能调控政策",
        summary="工信部发文拟对光伏行业实施产能总量控制，新建项目审批收紧",
        symbols=["601012", "688599", "002459"],
        sentiment_score=-0.85,
        event_type=FinancialEventType.POLICY,
        confidence=0.88,
        tags={"政策负面": "true"},
    )
    publisher = EventPublisher()
    ok = publisher.publish_one(event)
    logger.info(f"  发布结果: {'✓ 成功' if ok else '✗ 失败'}")
    logger.info("  预期: [EventRisk] 风控参数变更 trigger=news.policy")
    logger.info("  预期: totalExposure降至80%")
    return ok


def test_normal_news():
    """测试4: 普通新闻 → 不触发风控"""
    logger.info("=" * 60)
    logger.info("测试4: 普通新闻 (不应触发风控)")
    event = FinancialEvent(
        source="xueqiu",
        title="贵州茅台发布2025年Q1财报",
        summary="Q1营收同比增长15%，净利润同比增长18%",
        symbols=["600519"],
        sentiment_score=0.3,
        event_type=FinancialEventType.EARNINGS,
        confidence=0.75,
        tags={},
    )
    publisher = EventPublisher()
    ok = publisher.publish_one(event)
    logger.info(f"  发布结果: {'✓ 成功' if ok else '✗ 失败'}")
    logger.info("  预期: 无 [EventRisk] 风控参数变更日志")
    return ok


def test_batch_publish():
    """测试5: 批量发布"""
    logger.info("=" * 60)
    logger.info("测试5: 批量发布 (盘前/盘后场景)")
    events = [
        FinancialEvent(
            source="eastmoney",
            title=f"批量测试新闻 #{i}",
            summary=f"测试摘要 #{i}",
            symbols=[f"00000{i}"],
            sentiment_score=-0.5,
            event_type=FinancialEventType.ALERT,
            confidence=0.6,
        )
        for i in range(5)
    ]
    publisher = EventPublisher()
    success = publisher.publish_batch(events)
    logger.info(f"  批量发布: {success}/{len(events)} 成功")
    return success == len(events)


def main():
    logger.info("=" * 60)
    logger.info("新闻风控监控系统测试")
    logger.info("=" * 60)
    logger.info("前置条件: C++ app 已启动, EventRiskSubscriber 已订阅 news.*")

    results = []
    results.append(("立案调查封禁", test_investigation_block()))
    results.append(("ST警示封禁", test_st_warning()))
    results.append(("政策负面降敞口", test_policy_negative()))
    results.append(("普通新闻无影响", test_normal_news()))
    results.append(("批量发布", test_batch_publish()))

    logger.info("=" * 60)
    logger.info("测试汇总:")
    passed = 0
    for name, ok in results:
        status = "✓ 已发送" if ok else "✗ 发送失败"
        logger.info(f"  [{status}] {name}")
        if ok:
            passed += 1
    logger.info(f"发布成功: {passed}/{len(results)}")
    logger.info("")
    logger.info("验证步骤 (需观察 C++ app 日志):")
    logger.info("  1. 搜索 '[EventRisk] 已订阅 news.* 事件' — 确认订阅成功")
    logger.info("  2. 搜索 '[EventRisk] 风控参数变更' — 确认规则触发")
    logger.info("  3. 搜索 '002776' / '600804' — 确认封禁名单生效")
    logger.info("  4. 搜索 'totalExposure' — 确认敞口调整")


if __name__ == "__main__":
    main()

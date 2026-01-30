"""
商品价格传导分析示例
演示如何使用商品产业链分析器
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from astock_engine.data.commodity_chain import CommodityChainAnalyzer
from astock_engine.data.providers import FuturesDataProvider, StockDataProvider, DataQuery, DataType


def example_1_commodity_chain_analysis():
    """示例1: 商品产业链分析"""
    logger.info("=" * 60)
    logger.info("示例1: 商品价格产业链传导分析")
    logger.info("=" * 60)
    
    # 初始化分析器
    analyzer = CommodityChainAnalyzer()
    
    # 模拟商品价格数据
    commodities = ['RB', 'I', 'CU', 'AL', 'SC', 'M', 'C']
    dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
    
    data = []
    for commodity in commodities:
        base_price = np.random.randint(3000, 8000)
        prices = base_price * (1 + np.random.randn(30).cumsum() * 0.02)
        
        for i, date in enumerate(dates):
            data.append({
                'commodity': commodity,
                'date': date,
                'close': prices[i],
                'pct_change': (prices[i] - prices[i-1]) / prices[i-1] if i > 0 else 0
            })
    
    commodity_df = pd.DataFrame(data)
    
    # 显示最新价格变化
    logger.info("\n最新商品价格变化:")
    latest = commodity_df[commodity_df['date'] == commodity_df['date'].max()]
    logger.info(latest[['commodity', 'close', 'pct_change']].to_string(index=False))
    
    # 分析产业链影响
    impacts = analyzer.analyze_commodity_impact(commodity_df)
    
    logger.info(f"\n产业链影响分析:")
    logger.info(f"  上游受益机会: {len(impacts['upstream_benefits'])} 个")
    logger.info(f"  中游受益机会: {len(impacts['midstream_benefits'])} 个")
    logger.info(f"  下游成本压力: {len(impacts['downstream_pressure'])} 个")
    
    # 详细展示上游受益
    if impacts['upstream_benefits']:
        logger.info(f"\n【上游原材料受益详情】")
        for impact in impacts['upstream_benefits'][:3]:
            logger.info(f"\n  产业链: {impact['chain']}")
            logger.info(f"  商品: {impact['commodity']}")
            logger.info(f"  价格变化: {impact['price_change']:+.2%}")
            logger.info(f"  变化等级: {impact['change_level']}")
            logger.info(f"  影响方向: {impact['impact_direction']}")
            logger.info(f"  相关股票: {len(impact['affected_stocks'])} 只")
            if impact['affected_stocks']:
                logger.info(f"    {', '.join(impact['affected_stocks'][:5])}")


def example_2_price_transmission_path():
    """示例2: 价格传导路径分析"""
    logger.info("\n" + "=" * 60)
    logger.info("示例2: 价格传导路径分析")
    logger.info("=" * 60)
    
    analyzer = CommodityChainAnalyzer()
    
    # 分析螺纹钢价格传导
    commodity = 'RB'
    paths = analyzer.get_price_transmission_path(commodity)
    
    logger.info(f"\n{commodity} (螺纹钢) 价格传导路径:")
    
    for path in paths:
        logger.info(f"\n  产业链: {path['chain']}")
        for stage in path['stages']:
            logger.info(f"    └─ {stage['stage']}: {stage['impact']} 影响")
            if stage['stocks']:
                logger.info(f"       相关股票: {', '.join(stage['stocks'][:3])}...")


def example_3_find_beneficiaries():
    """示例3: 找出受益股票"""
    logger.info("\n" + "=" * 60)
    logger.info("示例3: 商品涨价受益股分析")
    logger.info("=" * 60)
    
    analyzer = CommodityChainAnalyzer()
    
    # 测试不同商品涨价的受益股
    scenarios = [
        ('RB', 'up', '螺纹钢涨价'),
        ('CU', 'up', '铜价上涨'),
        ('SC', 'up', '原油上涨'),
        ('M', 'down', '豆粕下跌'),
    ]
    
    for commodity, trend, description in scenarios:
        beneficiaries = analyzer.find_beneficiary_stocks(commodity, trend)
        
        logger.info(f"\n{description} ({commodity}):")
        logger.info(f"  受益股票数量: {len(beneficiaries)}")
        if beneficiaries:
            logger.info(f"  主要受益股: {', '.join(beneficiaries[:5])}")


def example_4_cost_pressure_analysis():
    """示例4: 行业成本压力分析"""
    logger.info("\n" + "=" * 60)
    logger.info("示例4: 行业成本压力指数")
    logger.info("=" * 60)
    
    analyzer = CommodityChainAnalyzer()
    
    # 模拟商品价格数据（原材料普遍上涨）
    commodity_df = pd.DataFrame({
        'commodity': ['I', 'J', 'SC', 'CU', 'M'],
        'date': [datetime.now()] * 5,
        'close': [800, 2200, 550, 68000, 3200],
        'pct_change': [0.08, 0.06, 0.12, 0.05, 0.07]  # 全部上涨
    })
    
    logger.info("\n原材料价格变化:")
    logger.info(commodity_df[['commodity', 'pct_change']].to_string(index=False))
    
    # 计算各行业成本压力
    industries = ['钢铁产业链', '石油化工产业链', '有色金属产业链', '农产品产业链']
    
    logger.info(f"\n行业成本压力指数 (0-1, 越高压力越大):")
    for industry in industries:
        pressure = analyzer.calculate_cost_pressure_index(commodity_df, industry)
        logger.info(f"  {industry}: {pressure:.2f} {'⚠️ 高压力' if pressure > 0.5 else ''}")


def example_5_realtime_commodity_tracking():
    """示例5: 实时商品价格追踪与选股"""
    logger.info("\n" + "=" * 60)
    logger.info("示例5: 实时商品价格追踪与股票选择")
    logger.info("=" * 60)
    
    try:
        # 初始化数据提供者
        futures_provider = FuturesDataProvider()
        futures_provider.initialize()
        
        analyzer = CommodityChainAnalyzer()
        
        # 获取期货实时行情
        logger.info("\n正在获取期货实时行情...")
        realtime_response = futures_provider.get_realtime_data(['RB', 'CU', 'AL'])
        
        if realtime_response.success and not realtime_response.data.empty:
            logger.info("\n实时期货行情:")
            logger.info(realtime_response.data[['symbol', 'price', 'change_pct']].to_string(index=False))
            
            # 转换为分析所需格式
            commodity_df = realtime_response.data.rename(columns={
                'symbol': 'commodity',
                'price': 'close',
                'change_pct': 'pct_change'
            })
            commodity_df['date'] = datetime.now()
            
            # 分析影响
            impacts = analyzer.analyze_commodity_impact(commodity_df)
            
            # 找出受益股票
            all_beneficiaries = set()
            for impact in impacts['upstream_benefits']:
                if impact['price_change'] > 0.03:  # 涨幅超过3%
                    stocks = impact['affected_stocks']
                    all_beneficiaries.update(stocks)
            
            if all_beneficiaries:
                logger.info(f"\n推荐关注的受益股票:")
                for stock in list(all_beneficiaries)[:10]:
                    logger.info(f"  • {stock}")
            else:
                logger.info(f"\n暂无显著受益机会")
        else:
            logger.warning("获取期货实时数据失败，使用模拟数据")
            
    except Exception as e:
        logger.error(f"实时追踪出错: {e}")


def example_6_generate_report():
    """示例6: 生成完整分析报告"""
    logger.info("\n" + "=" * 60)
    logger.info("示例6: 生成商品价格传导分析报告")
    logger.info("=" * 60)
    
    analyzer = CommodityChainAnalyzer()
    
    # 模拟商品价格数据
    commodity_df = pd.DataFrame({
        'commodity': ['RB', 'I', 'CU', 'SC', 'M'],
        'date': [datetime.now()] * 5,
        'close': [4200, 800, 68000, 550, 3200],
        'pct_change': [0.08, 0.05, -0.03, 0.12, 0.06]
    })
    
    # 生成报告
    report = analyzer.generate_commodity_report(commodity_df)
    
    logger.info("\n" + report)


def main():
    """主函数"""
    logger.info("商品价格传导分析系统")
    logger.info("=" * 60)
    
    try:
        example_1_commodity_chain_analysis()
        example_2_price_transmission_path()
        example_3_find_beneficiaries()
        example_4_cost_pressure_analysis()
        example_5_realtime_commodity_tracking()
        example_6_generate_report()
        
        logger.info("\n" + "=" * 60)
        logger.info("所有示例运行完成！")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"运行出错: {e}", exc_info=True)


if __name__ == "__main__":
    main()

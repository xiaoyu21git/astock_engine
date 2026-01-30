"""
完整示例：展示如何使用AStockQuantEngine的所有核心功能
包括：数据获取、异动监控、风险管理、策略回测
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入数据提供者
from astock_engine.data.providers import (
    StockDataProvider,
    FuturesDataProvider,
    NewsDataProvider,
    DataQuery,
    DataType
)

# 导入异动监控
from astock_engine.anomaly import AnomalyDetector, AnomalyEvent

# 导入风险管理
from astock_engine.risk import RiskManager, RiskAlert


def example_1_basic_data_fetching():
    """示例1: 基础数据获取"""
    logger.info("=" * 60)
    logger.info("示例1: 获取股票和期货数据")
    logger.info("=" * 60)
    
    # 初始化数据提供者
    stock_provider = StockDataProvider()
    stock_provider.initialize()
    
    # 查询参数
    query = DataQuery(
        symbols=['000001.SZ', '600000.SH'],  # 平安银行、浦发银行
        start_date=datetime(2024, 1, 1).date(),
        end_date=datetime(2024, 12, 31).date(),
        frequency='1d',
        adjust='qfq'
    )
    
    # 获取日线数据
    response = stock_provider.get_data(query, DataType.STOCK_DAILY)
    
    if response.success:
        logger.info(f"成功获取 {len(response.data)} 条数据")
        logger.info("\n" + response.data.head(10).to_string())
        
        # 统计信息
        for symbol in query.symbols:
            symbol_data = response.data[response.data['symbol'] == symbol]
            logger.info(f"\n{symbol} 统计:")
            logger.info(f"  数据条数: {len(symbol_data)}")
            logger.info(f"  价格范围: {symbol_data['close'].min():.2f} ~ {symbol_data['close'].max():.2f}")
            logger.info(f"  平均成交额: {symbol_data['amount'].mean()/100000000:.2f}亿")
    else:
        logger.error(f"数据获取失败: {response.error_msg}")


def example_2_realtime_monitoring():
    """示例2: 实时行情与异动监控"""
    logger.info("\n" + "=" * 60)
    logger.info("示例2: 实时行情监控与异动检测")
    logger.info("=" * 60)
    
    # 初始化
    stock_provider = StockDataProvider()
    stock_provider.initialize()
    
    anomaly_detector = AnomalyDetector()
    
    # 定义异动回调
    def on_anomaly(event: AnomalyEvent):
        logger.warning(f"🚨 异动预警: {event.description}")
        logger.warning(f"   股票: {event.symbol} | 类型: {event.anomaly_type.value}")
        logger.warning(f"   价格: {event.current_price:.2f} | 涨跌幅: {event.change_rate:.2f}%")
        logger.warning(f"   严重程度: {'⚠️' * event.severity}")
    
    # 订阅异动事件
    anomaly_detector.subscribe(on_anomaly)
    
    # 获取实时行情
    symbols = ['000001.SZ', '600000.SH', '600519.SH', '000858.SZ']
    response = stock_provider.get_realtime_data(symbols)
    
    if response.success and not response.data.empty:
        logger.info(f"获取到 {len(response.data)} 只股票的实时行情")
        logger.info("\n" + response.data[['symbol', 'name', 'price', 'pct_change', 'volume', 'turnover']].to_string())
        
        # 检测异动
        anomalies = anomaly_detector.detect(response.data)
        
        if anomalies:
            logger.info(f"\n检测到 {len(anomalies)} 个异动事件")
        else:
            logger.info("\n暂无异动")
        
        # 异动统计
        stats = anomaly_detector.get_anomaly_statistics()
        logger.info(f"\n异动统计:")
        logger.info(f"  24小时内异动总数: {stats['total_count']}")
        logger.info(f"  高严重性事件: {stats['high_severity_count']}")
        logger.info(f"  涉及股票数: {stats['symbols_affected']}")


def example_3_futures_basis_analysis():
    """示例3: 股指期货基差分析"""
    logger.info("\n" + "=" * 60)
    logger.info("示例3: 股指期货基差分析")
    logger.info("=" * 60)
    
    # 初始化期货数据提供者
    futures_provider = FuturesDataProvider()
    futures_provider.initialize()
    
    # 获取主力合约
    main_contracts = futures_provider.get_main_contracts(['IF', 'IH', 'IC'])
    logger.info(f"主力合约: {main_contracts}")
    
    # 获取基差数据（以IF为例）
    if 'IF' in main_contracts:
        basis_df = futures_provider.get_basis_data(
            index_symbol='000300.SH',  # 沪深300
            futures_symbol=main_contracts['IF']
        )
        
        if not basis_df.empty:
            logger.info(f"\n沪深300股指期货基差分析:")
            logger.info(f"  平均基差: {basis_df['basis'].mean():.2f} 点")
            logger.info(f"  基差率: {basis_df['basis_rate'].mean():.2%}")
            logger.info(f"  最大基差: {basis_df['basis'].max():.2f} 点")
            logger.info(f"  最小基差: {basis_df['basis'].min():.2f} 点")
            
            # 基差过大预警
            if abs(basis_df['basis_rate'].iloc[-1]) > 0.02:  # 2%
                logger.warning(f"⚠️ 当前基差率 {basis_df['basis_rate'].iloc[-1]:.2%} 超过2%，可能存在套利机会！")


def example_4_news_sentiment_analysis():
    """示例4: 新闻舆情分析"""
    logger.info("\n" + "=" * 60)
    logger.info("示例4: 新闻舆情分析")
    logger.info("=" * 60)
    
    # 初始化新闻提供者
    news_provider = NewsDataProvider()
    news_provider.initialize()
    
    # 获取市场新闻
    query = DataQuery(
        symbols=[],
        start_date=(datetime.now() - timedelta(days=7)).date(),
        end_date=datetime.now().date()
    )
    
    response = news_provider.get_data(query, DataType.NEWS)
    
    if response.success and not response.data.empty:
        logger.info(f"获取到 {len(response.data)} 条新闻")
        
        # 显示最新新闻
        latest_news = response.data.head(5)
        logger.info("\n最新5条新闻:")
        for idx, news in latest_news.iterrows():
            logger.info(f"\n[{news['publish_time']}] {news['title']}")
            logger.info(f"  来源: {news['source']}")
            
            # 简单情感分析
            sentiment = news_provider.analyze_sentiment(news['title'])
            logger.info(f"  情感: {sentiment['sentiment']} (得分: {sentiment['score']:.2f})")
    
    # 获取热门股票
    hot_stocks = news_provider.get_hot_stocks(limit=10)
    if not hot_stocks.empty:
        logger.info(f"\n热门股票 TOP 10:")
        logger.info(hot_stocks[['代码', '名称', '最新价', '涨跌幅']].to_string())


def example_5_risk_management():
    """示例5: 风险管理系统"""
    logger.info("\n" + "=" * 60)
    logger.info("示例5: 风险管理与监控")
    logger.info("=" * 60)
    
    # 初始化风险管理器
    risk_manager = RiskManager()
    
    # 定义风险预警回调
    def on_risk_alert(alert: RiskAlert):
        logger.error(f"💥 风险预警: {alert.alert_type}")
        logger.error(f"   等级: {alert.level.value}")
        logger.error(f"   信息: {alert.message}")
        logger.error(f"   建议: {alert.recommended_action}")
    
    # 订阅风险预警
    risk_manager.subscribe(on_risk_alert)
    
    # 模拟组合数据
    portfolio_value = 1000000  # 100万
    
    # 模拟持仓
    positions = {
        '000001.SZ': {
            'symbol': '000001.SZ',
            'quantity': 10000,
            'entry_price': 12.50,
            'current_price': 13.00,
            'market_value': 130000
        },
        '600000.SH': {
            'symbol': '600000.SH',
            'quantity': 20000,
            'entry_price': 8.00,
            'current_price': 7.50,
            'market_value': 150000
        }
    }
    
    # 模拟净值曲线
    dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
    equity_curve = pd.Series(
        index=dates,
        data=1000000 * (1 + np.random.randn(100).cumsum() * 0.01)
    )
    
    # 计算风险指标
    metrics = risk_manager.calculate_metrics(
        portfolio_value=portfolio_value,
        positions=positions,
        equity_curve=equity_curve
    )
    
    logger.info("\n风险指标:")
    logger.info(f"  组合净值: ¥{metrics.portfolio_value:,.2f}")
    logger.info(f"  总收益率: {metrics.total_return:.2%}")
    logger.info(f"  夏普比率: {metrics.sharpe_ratio:.2f}")
    logger.info(f"  最大回撤: {metrics.max_drawdown:.2%}")
    logger.info(f"  波动率: {metrics.volatility:.2%}")
    logger.info(f"  持仓集中度: {metrics.position_concentration:.2%}")
    logger.info(f"  风险等级: {metrics.risk_level.value}")
    
    # 检查风险限制
    alerts = risk_manager.check_limits(metrics, positions)
    
    if not alerts:
        logger.info("\n✅ 所有风险指标均在安全范围内")
    
    # 生成风险报告
    report = risk_manager.generate_risk_report(metrics)
    logger.info(f"\n完整风险报告: {report}")
    
    # 计算持仓规模建议
    symbol = '000001.SZ'
    price = 13.00
    volatility = 0.25
    suggested_shares = risk_manager.calculate_position_size(
        portfolio_value=portfolio_value,
        price=price,
        volatility=volatility
    )
    logger.info(f"\n仓位建议: {symbol} 建议持仓 {suggested_shares} 股")


def example_6_integrated_workflow():
    """示例6: 完整工作流程"""
    logger.info("\n" + "=" * 60)
    logger.info("示例6: 完整量化交易工作流程")
    logger.info("=" * 60)
    
    # 1. 初始化所有模块
    stock_provider = StockDataProvider()
    stock_provider.initialize()
    
    anomaly_detector = AnomalyDetector()
    risk_manager = RiskManager()
    
    # 2. 获取实时行情
    symbols = ['000001.SZ', '600000.SH', '600519.SH']
    realtime_response = stock_provider.get_realtime_data(symbols)
    
    if not realtime_response.success:
        logger.error("获取实时数据失败")
        return
    
    logger.info(f"\n✓ 获取到 {len(realtime_response.data)} 只股票实时行情")
    
    # 3. 异动检测
    anomalies = anomaly_detector.detect(realtime_response.data)
    logger.info(f"✓ 检测到 {len(anomalies)} 个异动")
    
    # 4. 模拟组合与风险计算
    portfolio_value = 1000000
    equity_curve = pd.Series(
        index=pd.date_range(end=datetime.now(), periods=100, freq='D'),
        data=1000000 * (1 + np.random.randn(100).cumsum() * 0.01)
    )
    
    positions = {}
    metrics = risk_manager.calculate_metrics(
        portfolio_value=portfolio_value,
        positions=positions,
        equity_curve=equity_curve
    )
    
    logger.info(f"✓ 风险评估完成，风险等级: {metrics.risk_level.value}")
    
    # 5. 综合决策
    logger.info("\n" + "=" * 40)
    logger.info("交易决策建议:")
    logger.info("=" * 40)
    
    for _, stock in realtime_response.data.iterrows():
        symbol = stock['symbol']
        name = stock['name']
        price = stock['price']
        pct_change = stock['pct_change']
        
        # 检查是否有异动
        has_anomaly = any(a.symbol == symbol for a in anomalies)
        
        # 计算建议仓位
        suggested_shares = risk_manager.calculate_position_size(
            portfolio_value=portfolio_value,
            price=price,
            volatility=0.25
        )
        
        logger.info(f"\n{symbol} ({name})")
        logger.info(f"  当前价格: ¥{price:.2f} ({pct_change:+.2f}%)")
        logger.info(f"  异动状态: {'⚠️ 有异动' if has_anomaly else '✅ 正常'}")
        logger.info(f"  建议仓位: {suggested_shares} 股 (约¥{suggested_shares * price:,.0f})")
    
    logger.info("\n" + "=" * 60)
    logger.info("工作流程完成！")
    logger.info("=" * 60)


def main():
    """主函数"""
    try:
        # 运行所有示例
        example_1_basic_data_fetching()
        example_2_realtime_monitoring()
        example_3_futures_basis_analysis()
        example_4_news_sentiment_analysis()
        example_5_risk_management()
        example_6_integrated_workflow()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 所有示例运行完成！")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"运行出错: {e}", exc_info=True)


if __name__ == "__main__":
    main()

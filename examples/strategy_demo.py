"""
策略系统完整测试示例
演示如何使用各种策略进行交易
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

# 导入策略
from astock_engine.strategies import (
    MultiFactorStrategy,
    IndexFuturesArbitrageStrategy,
    CommodityDrivenStrategy,
    SentimentDrivenStrategy
)

# 导入数据提供者
from astock_engine.data.providers import (
    StockDataProvider,
    FuturesDataProvider,
    NewsDataProvider,
    DataQuery,
    DataType
)


def test_multi_factor_strategy():
    """测试多因子选股策略"""
    logger.info("=" * 60)
    logger.info("测试1: 多因子选股策略")
    logger.info("=" * 60)
    
    # 初始化策略
    strategy = MultiFactorStrategy(params={
        'initial_capital': 1000000,
        'technical_weight': 0.4,
        'volume_weight': 0.3,
        'sentiment_weight': 0.3,
        'buy_threshold': 0.6,
        'topN': 5
    })
    
    # 初始化数据提供者
    stock_provider = StockDataProvider()
    stock_provider.initialize()
    
    # 获取股票数据
    symbols = ['000001.SZ', '600000.SH', '600519.SH', '000858.SZ', '600036.SH']
    query = DataQuery(
        symbols=symbols,
        start_date=(datetime.now() - timedelta(days=30)).date(),
        end_date=datetime.now().date()
    )
    
    response = stock_provider.get_data(query, DataType.STOCK_DAILY)
    
    if not response.success:
        logger.error("Failed to get stock data")
        return
    
    data = response.data
    logger.info(f"Got {len(data)} data points for {len(symbols)} stocks")
    
    # 生成信号
    signals = strategy.generate_signals(data)
    
    logger.info(f"Generated {len(signals)} signals:")
    for signal in signals:
        logger.info(f"  {signal.symbol}: {signal.direction} @ {signal.price:.2f}, "
                   f"strength {signal.strength:.2f}, reason: {signal.reason}")
    
    # 获取当前价格
    realtime_response = stock_provider.get_realtime_data(symbols)
    current_prices = {}
    if realtime_response.success:
        for _, row in realtime_response.data.iterrows():
            current_prices[row['symbol']] = row['price']
    
    # 执行信号
    if signals and current_prices:
        strategy.execute_signals(signals, current_prices)
        
        # 显示持仓
        positions_df = strategy.get_positions_summary()
        if not positions_df.empty:
            logger.info(f"\nCurrent positions:")
            logger.info(positions_df.to_string())
        
        # 显示绩效
        metrics = strategy.get_performance_metrics(current_prices)
        logger.info(f"\nPerformance metrics:")
        for key, value in metrics.items():
            if isinstance(value, float):
                logger.info(f"  {key}: {value:.2f}")
            else:
                logger.info(f"  {key}: {value}")


def test_commodity_strategy():
    """测试商品期货选股策略"""
    logger.info("\n" + "=" * 60)
    logger.info("测试2: 商品期货选股策略")
    logger.info("=" * 60)
    
    # 初始化策略
    strategy = CommodityDrivenStrategy(params={
        'initial_capital': 1000000,
        'price_change_threshold': 0.03,  # 3%
    })
    
    # 准备股票数据
    stock_provider = StockDataProvider()
    stock_provider.initialize()
    
    steel_stocks = ['600019.SH', '000709.SZ']  # 宝钢、河钢
    query = DataQuery(
        symbols=steel_stocks,
        start_date=(datetime.now() - timedelta(days=5)).date()
    )
    
    response = stock_provider.get_data(query, DataType.STOCK_DAILY)
    
    if not response.success:
        logger.error("Failed to get stock data")
        return
    
    # 模拟商品期货价格变化
    commodity_prices = pd.DataFrame({
        'commodity': ['RB', 'CU', 'SC'],
        'price': [4200, 68000, 550],
        'pct_change': [0.05, -0.02, 0.04]  # 螺纹钢涨5%, 铜跌2%, 原油涨4%
    })
    
    logger.info(f"Commodity price changes:")
    logger.info(commodity_prices.to_string())
    
    # 生成信号
    context = {'commodity_prices': commodity_prices}
    signals = strategy.generate_signals(response.data, context)
    
    logger.info(f"\nGenerated {len(signals)} signals:")
    for signal in signals:
        logger.info(f"  {signal.symbol}: {signal.direction} @ {signal.price:.2f}, "
                   f"reason: {signal.reason}")
        logger.info(f"    metadata: {signal.metadata}")


def test_sentiment_strategy():
    """测试舆情驱动策略"""
    logger.info("\n" + "=" * 60)
    logger.info("测试3: 舆情驱动策略")
    logger.info("=" * 60)
    
    # 初始化策略
    strategy = SentimentDrivenStrategy(params={
        'initial_capital': 1000000,
        'sentiment_threshold': 0.7,
        'holding_period': 5
    })
    
    # 准备数据
    stock_provider = StockDataProvider()
    stock_provider.initialize()
    
    symbols = ['600519.SH', '000858.SZ']
    query = DataQuery(symbols=symbols)
    response = stock_provider.get_data(query, DataType.STOCK_DAILY)
    
    # 模拟新闻数据
    news_data = pd.DataFrame({
        'symbol': ['600519.SH', '600519.SH', '000858.SZ'],
        'title': [
            '贵州茅台业绩预增30%',
            '茅台新产品发布会成功举办',
            '五粮液签署重大合作协议'
        ],
        'publish_time': [datetime.now()] * 3,
        'sentiment': ['positive', 'positive', 'positive'],
        'score': [0.85, 0.75, 0.80]
    })
    
    # 模拟热门股票
    hot_stocks = pd.DataFrame({
        '代码': ['600519.SH', '000858.SZ'],
        '名称': ['贵州茅台', '五粮液'],
        '热度': [2500, 1800],
        '涨跌幅': [2.5, 1.8]
    })
    
    logger.info("News data:")
    logger.info(news_data[['symbol', 'title', 'sentiment', 'score']].to_string())
    
    logger.info("\nHot stocks:")
    logger.info(hot_stocks.to_string())
    
    # 生成信号
    context = {
        'news_data': news_data,
        'hot_stocks': hot_stocks
    }
    
    signals = strategy.generate_signals(response.data, context)
    
    logger.info(f"\nGenerated {len(signals)} signals:")
    for signal in signals:
        logger.info(f"  {signal.symbol}: {signal.direction} @ {signal.price:.2f}")
        logger.info(f"    reason: {signal.reason}")
        logger.info(f"    metadata: {signal.metadata}")


def test_futures_arbitrage_strategy():
    """测试股指期货套利策略"""
    logger.info("\n" + "=" * 60)
    logger.info("测试4: 股指期货套利策略")
    logger.info("=" * 60)
    
    # 初始化策略
    strategy = IndexFuturesArbitrageStrategy(params={
        'initial_capital': 1000000,
        'basis_threshold': 0.02,  # 2%
        'index_symbol': '000300.SH'
    })
    
    # 准备数据
    stock_provider = StockDataProvider()
    stock_provider.initialize()
    
    # 获取成分股数据
    basket = ['600519.SH', '600036.SH', '601318.SH']
    query = DataQuery(symbols=basket)
    response = stock_provider.get_data(query, DataType.STOCK_DAILY)
    
    # 模拟基差数据
    dates = pd.date_range(end=datetime.now(), periods=10, freq='D')
    basis_data = pd.DataFrame({
        'date': dates,
        'close_index': np.linspace(3800, 3850, 10),
        'close_futures': np.linspace(3880, 3900, 10)
    })
    basis_data['basis'] = basis_data['close_futures'] - basis_data['close_index']
    basis_data['basis_rate'] = basis_data['basis'] / basis_data['close_index']
    
    logger.info("Basis data:")
    logger.info(basis_data[['date', 'basis', 'basis_rate']].tail().to_string())
    
    latest_basis_rate = basis_data['basis_rate'].iloc[-1]
    logger.info(f"\nLatest basis rate: {latest_basis_rate:.2%}")
    
    # 生成信号
    context = {'basis_data': basis_data}
    signals = strategy.generate_signals(response.data, context)
    
    logger.info(f"\nGenerated {len(signals)} signals:")
    for signal in signals[:5]:  # 只显示前5个
        logger.info(f"  {signal.symbol}: {signal.direction}, reason: {signal.reason}")


def test_strategy_comparison():
    """比较不同策略的表现"""
    logger.info("\n" + "=" * 60)
    logger.info("测试5: 策略对比分析")
    logger.info("=" * 60)
    
    strategies = {
        'Multi-Factor': MultiFactorStrategy(params={'initial_capital': 1000000}),
        'Commodity': CommodityDrivenStrategy(params={'initial_capital': 1000000}),
        'Sentiment': SentimentDrivenStrategy(params={'initial_capital': 1000000})
    }
    
    logger.info("Strategy comparison:")
    logger.info(f"{'Strategy':<20} {'Capital':<15} {'Max Positions':<15}")
    logger.info("-" * 50)
    
    for name, strategy in strategies.items():
        logger.info(f"{name:<20} ${strategy.initial_capital:<14,.0f} {strategy.max_positions:<15}")
    
    logger.info(f"\nAll {len(strategies)} strategies initialized successfully!")


def main():
    """主函数"""
    try:
        logger.info("Starting Strategy System Tests")
        logger.info("=" * 60)
        
        # 运行所有测试
        test_multi_factor_strategy()
        test_commodity_strategy()
        test_sentiment_strategy()
        test_futures_arbitrage_strategy()
        test_strategy_comparison()
        
        logger.info("\n" + "=" * 60)
        logger.info("All strategy tests completed successfully!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()

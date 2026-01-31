"""
风控模块测试
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import datetime, timedelta
import logging

from astock_engine.risk import RiskManager, RiskConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)


def test_position_control():
    """测试仓位控制"""
    print("\n" + "="*60)
    print("测试1: 仓位控制".center(60))
    print("="*60 + "\n")
    
    config = RiskConfig(
        max_position_size=0.30,
        max_positions=10,
        max_total_exposure=0.95
    )
    
    manager = RiskManager(config)
    manager.initialize(1_000_000)
    
    # 测试1：正常开仓
    print("📝 测试正常开仓...")
    can_open, reason = manager.check_open_order('600519.SH', 1000, 100)
    print(f"   开仓600519.SH × 1000 @ ¥100: {can_open} - {reason}")
    assert can_open, "正常开仓应该允许"
    
    manager.add_position('600519.SH', 1000, 100, datetime.now())
    
    # 测试2：超过单股仓位
    print("\n📝 测试超过单股仓位...")
    can_open, reason = manager.check_open_order('000858.SZ', 5000, 100)
    print(f"   开仓000858.SZ × 5000 @ ¥100: {can_open} - {reason}")
    assert not can_open, "超过单股仓位应该拒绝"
    
    # 测试3：添加更多持仓
    print("\n📝 测试添加多个持仓...")
    for i in range(9):
        symbol = f"00000{i}.SZ"
        manager.add_position(symbol, 300, 100, datetime.now())
    
    print(f"   当前持仓数: {len(manager.positions)}")
    print(f"   总仓位: {manager.get_position_exposure():.2%}")
    
    # 测试4：超过最大持仓数
    print("\n📝 测试超过最大持仓数...")
    can_open, reason = manager.check_open_order('999999.SZ', 100, 100)
    print(f"   开仓999999.SZ: {can_open} - {reason}")
    assert not can_open, "超过最大持仓数应该拒绝"
    
    print("\n✅ 仓位控制测试通过\n")


def test_stop_loss():
    """测试止损"""
    print("\n" + "="*60)
    print("测试2: 止损功能".center(60))
    print("="*60 + "\n")
    
    config = RiskConfig(
        stop_loss=-0.05,
        trailing_stop=0.10
    )
    
    manager = RiskManager(config)
    manager.initialize(1_000_000)
    
    # 开仓
    manager.add_position('600519.SH', 1000, 100, datetime.now())
    
    # 测试1：正常持仓（不触发止损）
    print("📝 测试正常持仓...")
    manager.update_position_price('600519.SH', 98)
    should_stop, reason = manager.check_stop_loss('600519.SH')
    print(f"   价格下跌到¥98(-2%): {should_stop} - {reason}")
    assert not should_stop, "未达止损线不应触发"
    
    # 测试2：触发固定止损
    print("\n📝 测试触发固定止损...")
    manager.update_position_price('600519.SH', 94)
    should_stop, reason = manager.check_stop_loss('600519.SH')
    print(f"   价格下跌到¥94(-6%): {should_stop} - {reason}")
    assert should_stop, "达到止损线应该触发"
    
    # 重新开仓测试移动止损
    manager.remove_position('600519.SH', 94)
    manager.add_position('000858.SZ', 1000, 100, datetime.now())
    
    # 测试3：价格上涨
    print("\n📝 测试移动止损...")
    manager.update_position_price('000858.SZ', 120)
    print(f"   价格上涨到¥120(+20%), 最高价={manager.positions['000858.SZ'].highest_price}")
    
    # 测试4：触发移动止损
    manager.update_position_price('000858.SZ', 106)
    should_stop, reason = manager.check_stop_loss('000858.SZ')
    trailing_loss = manager.positions['000858.SZ'].trailing_loss
    print(f"   价格回落到¥106, 从最高点回撤={trailing_loss:.2%}: {should_stop} - {reason}")
    assert should_stop, "从最高点回撤超10%应触发移动止损"
    
    print("\n✅ 止损功能测试通过\n")


def test_take_profit():
    """测试止盈"""
    print("\n" + "="*60)
    print("测试3: 止盈功能".center(60))
    print("="*60 + "\n")
    
    config = RiskConfig(
        take_profit=0.20
    )
    
    manager = RiskManager(config)
    manager.initialize(1_000_000)
    
    manager.add_position('600519.SH', 1000, 100, datetime.now())
    
    # 测试1：未达止盈
    print("📝 测试未达止盈...")
    manager.update_position_price('600519.SH', 115)
    should_profit, reason = manager.check_take_profit('600519.SH')
    print(f"   价格上涨到¥115(+15%): {should_profit} - {reason}")
    assert not should_profit, "未达止盈线不应触发"
    
    # 测试2：触发止盈
    print("\n📝 测试触发止盈...")
    manager.update_position_price('600519.SH', 125)
    should_profit, reason = manager.check_take_profit('600519.SH')
    print(f"   价格上涨到¥125(+25%): {should_profit} - {reason}")
    assert should_profit, "达到止盈线应该触发"
    
    print("\n✅ 止盈功能测试通过\n")


def test_drawdown_limit():
    """测试回撤限制"""
    print("\n" + "="*60)
    print("测试4: 回撤限制".center(60))
    print("="*60 + "\n")
    
    config = RiskConfig(
        max_drawdown=-0.15,
        max_daily_loss=-0.03
    )
    
    manager = RiskManager(config)
    manager.initialize(1_000_000)
    
    # 开仓并亏损
    manager.add_position('600519.SH', 8000, 100, datetime.now())
    
    # 测试1：轻微亏损
    print("📝 测试轻微亏损...")
    manager.update_position_price('600519.SH', 95)
    drawdown = manager.get_current_drawdown()
    print(f"   价格下跌到¥95, 当前回撤={drawdown:.2%}")
    can_open, reason = manager.check_open_order('000858.SZ', 1000, 50)
    print(f"   尝试新开仓: {can_open} - {reason}")
    
    # 测试2：达到最大回撤
    print("\n📝 测试达到最大回撤...")
    manager.update_position_price('600519.SH', 83)
    drawdown = manager.get_current_drawdown()
    print(f"   价格下跌到¥83, 当前回撤={drawdown:.2%}")
    can_open, reason = manager.check_open_order('000858.SZ', 1000, 50)
    print(f"   尝试新开仓: {can_open} - {reason}")
    assert not can_open, "达到最大回撤应禁止新开仓"
    
    # 测试3：单日亏损限制
    print("\n📝 测试单日亏损限制...")
    manager.start_new_day()
    manager.update_position_price('600519.SH', 80)
    daily_return = manager.get_daily_return()
    print(f"   价格继续下跌到¥80, 单日亏损={daily_return:.2%}")
    can_open, reason = manager.check_open_order('000858.SZ', 1000, 50)
    print(f"   尝试新开仓: {can_open} - {reason}")
    assert not can_open, "单日亏损超限应禁止新开仓"
    
    print("\n✅ 回撤限制测试通过\n")


def test_risk_report():
    """测试风控报告"""
    print("\n" + "="*60)
    print("测试5: 风控报告".center(60))
    print("="*60 + "\n")
    
    config = RiskConfig()
    manager = RiskManager(config)
    manager.initialize(1_000_000)
    
    # 建立多个持仓
    manager.add_position('600519.SH', 1000, 100, datetime.now())
    manager.add_position('000858.SZ', 2000, 50, datetime.now())
    manager.add_position('002475.SZ', 500, 80, datetime.now())
    
    # 更新价格
    manager.update_position_price('600519.SH', 110)
    manager.update_position_price('000858.SZ', 48)
    manager.update_position_price('002475.SZ', 85)
    
    # 获取报告
    report = manager.get_risk_report()
    
    print("📊 风控报告:")
    print(f"   总资产: ¥{report['total_equity']:,.2f}")
    print(f"   可用资金: ¥{report['cash']:,.2f}")
    print(f"   持仓数: {report['position_count']}")
    print(f"   总仓位: {report['position_exposure']:.2%}")
    print(f"   当前回撤: {report['current_drawdown']:.2%}")
    print(f"   总收益率: {report['total_return']:.2%}")
    
    print(f"\n📋 持仓明细:")
    for symbol, pos in report['positions'].items():
        print(f"   {symbol}: {pos['quantity']}股 @ ¥{pos['current_price']:.2f}, "
              f"盈亏={pos['pnl']:+,.2f}({pos['pnl_pct']:+.2%}), "
              f"仓位={pos['ratio']:.2%}")
    
    print("\n✅ 风控报告测试通过\n")


def main():
    print("\n" + "="*60)
    print("风控模块功能测试".center(60))
    print("="*60)
    
    try:
        test_position_control()
        test_stop_loss()
        test_take_profit()
        test_drawdown_limit()
        test_risk_report()
        
        print("\n" + "="*60)
        print("🎉 所有测试通过！".center(60))
        print("="*60 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}\n")
    except Exception as e:
        print(f"\n❌ 测试异常: {e}\n")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()

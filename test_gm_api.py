#!/usr/bin/env python3
import os
import json
import schedule
import time
import pandas as pd
from datetime import datetime, time as dt_time, timedelta

# 掘金API导入（假设已安装 gm.api）
try:
    import gm.api as gm
except ImportError:
    print("未安装 gm.api，请先安装掘金Python SDK: pip install gm.api")
    exit(1)

def load_config():
    """读取 config/config.json 并兼容 juejin 字段结构"""
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../config/config.json'))
    if not os.path.exists(config_path):
        raise FileNotFoundError(f'配置文件未找到: {config_path}')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    if 'juejin' in config:
        token = config['juejin'].get('token')
        account_id = config['juejin'].get('account_id')
    else:
        token = config.get('token')
        account_id = config.get('account_id')
    if not token:
        raise ValueError('未在 config/config.json 的 juejin 字段中找到 token')
    return token, account_id

class TradingBot:
    def __init__(self, token, account_id, symbols=None, trading_hours=None):
        self.token = token
        self.account_id = account_id
        self.symbols = symbols or ["SHSE.600000", "SZSE.000001"]
        self.trading_hours = trading_hours or {'start': '09:30', 'end': '14:55'}
        self.setup_gm()
        self.test_results = []

    def setup_gm(self):
        """设置掘金API"""
        gm.set_token(self.token)
        print(f"[{datetime.now()}] GM API初始化完成")

    def check_trading_hours(self):
        """检查是否在交易时间内"""
        now = datetime.now()
        current_time = now.time()
        start_str = self.trading_hours['start']
        end_str = self.trading_hours['end']
        start_time = dt_time(*map(int, start_str.split(':')))
        end_time = dt_time(*map(int, end_str.split(':')))
        # 检查是否是交易日（简单版，实际需要更复杂的判断）
        if now.weekday() >= 5:  # 5=周六, 6=周日
            return False
        return start_time <= current_time <= end_time

    def get_account_info(self):
        """获取账户信息"""
        try:
            # 掘金SDK最新版本需要指定账户ID
            account = gm.account(account=self.account_id)
            return {
                'total': account.get('total', 0),
                'available': account.get('available', 0),
                'market_value': account.get('market_value', 0),
                'frozen': account.get('frozen', 0),
                'profit': account.get('profit', 0)
            }
        except Exception as e:
            print(f"[{datetime.now()}] 获取账户信息失败: {e}")
            return None

    def get_positions(self):
        """获取持仓"""
        try:
            # 掘金SDK最新版本需要指定账户ID
            positions = gm.positions(account=self.account_id)
            return positions
        except Exception as e:
            print(f"[{datetime.now()}] 获取持仓失败: {e}")
            return []
    
    def get_market_data(self, symbol, fields=None):
        """获取市场数据"""
        try:
            fields = fields or ["symbol", "last", "volume", "amount", "open", "high", "low", "pre_close"]
            data = gm.current(symbols=symbol, fields=fields)
            return data
        except Exception as e:
            print(f"获取市场数据失败: {e}")
            return None
    
    def get_history_data(self, symbol, start_time, end_time, frequency="1d", fields=None):
        """获取历史数据"""
        try:
            fields = fields or ["symbol", "open", "high", "low", "close", "volume", "amount"]
            data = gm.history(symbol=symbol, start_time=start_time, end_time=end_time, 
                            frequency=frequency, fields=fields, adjust=gm.ADJUST_PREV)
            return pd.DataFrame(data)
        except Exception as e:
            print(f"获取历史数据失败: {e}")
            return None
    
    def get_order_list(self):
        """获取订单列表"""
        try:
            orders = gm.orders(account=self.account_id)
            return orders
        except Exception as e:
            print(f"获取订单列表失败: {e}")
            return []
    
    def cancel_order(self, order_id):
        """取消订单"""
        try:
            result = gm.cancel_order(order_id)
            print(f"取消订单成功: {order_id}")
            return result
        except Exception as e:
            print(f"取消订单失败: {e}")
            return None
    
    def get_trading_calendar(self, start_date, end_date):
        """获取交易日历"""
        try:
            calendar = gm.get_trading_dates(exchange="SHSE", start_date=start_date, end_date=end_date)
            return calendar
        except Exception as e:
            print(f"获取交易日历失败: {e}")
            return None

    def place_order(self, symbol, volume, side='BUY', price=None):
        """下单函数"""
        try:
            if not price:
                # 获取当前价
                current = gm.current(symbols=symbol)
                if current:
                    price = current[0]['price']
                else:
                    return None
            
            # 使用正确的常量名
            order_type = gm.OrderType_LMT if price else gm.OrderType_MTL
            
            # 掘金SDK最新下单API
            order = gm.order_volume(
                symbol=symbol,
                volume=volume,
                side=gm.Side_Buy if side == 'BUY' else gm.Side_Sell,
                order_type=order_type,
                position_effect=gm.PositionEffect_Open,
                price=price,
                account=self.account_id
            )
            
            print(f"[{datetime.now()}] 下单: {symbol} {side} {volume} @ {price}")
            return order
            
        except Exception as e:
            print(f"[{datetime.now()}] 下单失败: {e}")
            return None
    
    def strategy_logic(self):
        """策略逻辑 - 双均线交叉策略"""
        if not self.check_trading_hours():
            return
        
        # 获取账户信息
        account = self.get_account_info()
        if account:
            print(f"[{datetime.now()}] 账户状态: 总资产={account['total']:.2f}, 可用={account['available']:.2f}, 持仓市值={account['market_value']:.2f}")
        
        # 获取持仓
        positions = self.get_positions()
        if positions:
            print(f"[{datetime.now()}] 持仓数量: {len(positions)}")
            for pos in positions[:3]:  # 显示前3个持仓
                print(f"    持仓: {pos.get('symbol')}, 数量: {pos.get('volume')}, 成本: {pos.get('cost', 0):.2f}")
        
        # 对每个股票执行策略
        for symbol in self.symbols:
            try:
                # 获取历史数据用于计算技术指标
                end_time = datetime.now()
                start_time = end_time - timedelta(days=60)  # 获取60天数据
                
                # 获取历史K线数据
                history_data = self.get_history_data(
                    symbol, 
                    start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    end_time.strftime("%Y-%m-%d %H:%M:%S"),
                    frequency="1d"
                )
                
                if history_data is None or history_data.empty:
                    print(f"[{datetime.now()}] 无法获取 {symbol} 的历史数据")
                    continue
                
                # 确保有足够的数据
                if len(history_data) < 30:
                    print(f"[{datetime.now()}] {symbol} 数据不足，需要至少30条数据，当前{len(history_data)}条")
                    continue
                
                # 计算技术指标：双均线
                short_window = 10  # 短期均线窗口
                long_window = 30   # 长期均线窗口
                
                # 计算均线
                history_data['MA_short'] = history_data['close'].rolling(window=short_window).mean()
                history_data['MA_long'] = history_data['close'].rolling(window=long_window).mean()
                
                # 获取最新数据
                latest_data = history_data.iloc[-1]
                prev_data = history_data.iloc[-2] if len(history_data) > 1 else latest_data
                
                current_price = latest_data['close']
                ma_short_current = latest_data['MA_short']
                ma_long_current = latest_data['MA_long']
                ma_short_prev = prev_data['MA_short']
                ma_long_prev = prev_data['MA_long']
                
                # 检查是否持仓
                holding = any(pos.get('symbol') == symbol for pos in positions)
                
                # 生成交易信号
                # 金叉：短期均线上穿长期均线
                if (ma_short_prev <= ma_long_prev and ma_short_current > ma_long_current):
                    if not holding:
                        print(f"[{datetime.now()}] 🔔 {symbol} 金叉信号: MA{short_window}={ma_short_current:.2f} > MA{long_window}={ma_long_current:.2f}")
                        
                        # 计算买入数量（使用可用资金的20%）
                        if account and account['available'] > 0:
                            buy_amount = account['available'] * 0.2
                            volume = int(buy_amount / current_price / 100) * 100  # 100股整数倍
                            if volume >= 100:
                                print(f"[{datetime.now()}] 📈 执行买入: {symbol} {volume}股 @ {current_price:.2f}")
                                self.place_order(symbol, volume, side='BUY', price=current_price)
                
                # 死叉：短期均线下穿长期均线
                elif (ma_short_prev >= ma_long_prev and ma_short_current < ma_long_current):
                    if holding:
                        print(f"[{datetime.now()}] 🔔 {symbol} 死叉信号: MA{short_window}={ma_short_current:.2f} < MA{long_window}={ma_long_current:.2f}")
                        
                        # 查找持仓数量
                        for pos in positions:
                            if pos.get('symbol') == symbol:
                                volume = pos.get('volume', 0)
                                if volume > 0:
                                    print(f"[{datetime.now()}] 📉 执行卖出: {symbol} {volume}股 @ {current_price:.2f}")
                                    self.place_order(symbol, volume, side='SELL', price=current_price)
                                break
                
                # 打印当前状态
                print(f"[{datetime.now()}] {symbol}: 价格={current_price:.2f}, MA{short_window}={ma_short_current:.2f}, MA{long_window}={ma_long_current:.2f}, 持仓={'是' if holding else '否'}")
                
            except Exception as e:
                print(f"[{datetime.now()}] 处理 {symbol} 时出错: {e}")
                import traceback
                traceback.print_exc()
    
    def run_comprehensive_test(self):
        """运行全面的API测试"""
        print("=== 开始掘金SDK全面测试 ===")
        
        # 1. 测试账户信息
        print("\n1. 测试账户信息...")
        account_info = self.get_account_info()
        if account_info:
            print(f"账户信息: {account_info}")
            self.test_results.append("账户信息测试: 通过")
        else:
            self.test_results.append("账户信息测试: 失败")
        
        # 2. 测试持仓信息
        print("\n2. 测试持仓信息...")
        positions = self.get_positions()
        print(f"持仓数量: {len(positions)}")
        if positions:
            for pos in positions[:3]:  # 只显示前3个持仓
                print(f"持仓: {pos.get('symbol')}, 数量: {pos.get('volume')}")
        self.test_results.append("持仓信息测试: 通过")
        
        # 3. 测试市场数据
        print("\n3. 测试市场数据...")
        for symbol in self.symbols[:2]:  # 测试前2个标的
            market_data = self.get_market_data(symbol)
            if market_data:
                print(f"{symbol} 市场数据: {market_data}")
                self.test_results.append(f"{symbol}市场数据测试: 通过")
            else:
                self.test_results.append(f"{symbol}市场数据测试: 失败")
        
        # 4. 测试历史数据
        print("\n4. 测试历史数据...")
        end_time = datetime.now()
        start_time = end_time - timedelta(days=30)
        history_data = self.get_history_data(self.symbols[0], start_time.strftime("%Y-%m-%d"), 
                                           end_time.strftime("%Y-%m-%d"))
        if history_data is not None and not history_data.empty:
            print(f"历史数据行数: {len(history_data)}")
            print(f"最新数据:\n{history_data.tail(3)}")
            self.test_results.append("历史数据测试: 通过")
        else:
            self.test_results.append("历史数据测试: 失败")
        
        # 5. 测试订单列表
        print("\n5. 测试订单列表...")
        orders = self.get_order_list()
        print(f"订单数量: {len(orders)}")
        self.test_results.append("订单列表测试: 通过")
        
        # 6. 测试交易日历
        print("\n6. 测试交易日历...")
        calendar = self.get_trading_calendar("2024-01-01", "2024-12-31")
        if calendar:
            print(f"2024年交易日数量: {len(calendar)}")
            print(f"前5个交易日: {calendar[:5]}")
            self.test_results.append("交易日历测试: 通过")
        else:
            self.test_results.append("交易日历测试: 失败")
        
        print("\n=== 测试完成 ===")
        print("测试结果汇总:")
        for result in self.test_results:
            print(f"- {result}")
        
        return self.test_results

    def run(self):
        """运行机器人"""
        print(f"[{datetime.now()}] 交易机器人启动")
        
        # 使用schedule定时运行
        schedule.every(60).seconds.do(self.strategy_logic)  # 每60秒运行一次
        
        while True:
            try:
                schedule.run_pending()
                time.sleep(1)
            except KeyboardInterrupt:
                print("\n用户中断，退出程序")
                break
            except Exception as e:
                print(f"[{datetime.now()}] 错误: {e}")
                time.sleep(10)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='掘金SDK测试工具')
    parser.add_argument('--test', action='store_true', help='运行全面测试')
    parser.add_argument('--create-config', action='store_true', help='创建示例配置文件')
    parser.add_argument('--symbols', nargs='+', help='指定测试的股票代码')
    
    args = parser.parse_args()
    
    if args.create_config:
        # 创建示例配置文件
        config = {
            "juejin": {
                "token": "your_gm_token_here",
                "account_id": "your_account_id_here"
            },
            "symbols": ["SHSE.600000", "SZSE.000001"],
            "trading_hours": {
                "start": "09:30",
                "end": "14:55"
            }
        }
        
        config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../config'))
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, 'config.json')
        
        if not os.path.exists(config_path):
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            print(f"示例配置文件已创建: {config_path}")
            print("请编辑该文件，填入您的掘金token和账户ID")
        else:
            print(f"配置文件已存在: {config_path}")
        exit(0)
    
    # 自动读取 config/config.json juejin 字段
    try:
        token, account_id = load_config()
    except (FileNotFoundError, ValueError) as e:
        print(f"错误: {e}")
        print("请先创建配置文件或使用 --create-config 参数创建示例配置文件")
        exit(1)
    
    # 创建交易机器人
    symbols = args.symbols if args.symbols else None
    bot = TradingBot(token=token, account_id=account_id, symbols=symbols)
    
    if args.test:
        # 运行全面测试
        bot.run_comprehensive_test()
    else:
        # 默认行为：测试基本功能
        try:
            # 检查token和account_id是否有效
            if not token or token == 'your_gm_token':
                print("❌ 请先在config/config.json中配置有效的掘金token")
                exit(1)
            
            if not account_id or account_id == 'your_account_id':
                print("❌ 请先在config/config.json中配置有效的账户ID")
                exit(1)
                
            # 测试基本功能
            print("=== 掘金SDK基本功能测试 ===")
            
            # 查询账户信息
            account_info = bot.get_account_info()
            if account_info:
                print(f"✅ 账户信息: {account_info}")
            else:
                print("❌ 获取账户信息失败")
            
            # 查询持仓
            positions = bot.get_positions()
            if positions is not None:
                print(f"✅ 持仓数量: {len(positions)}")
                if positions:
                    for pos in positions[:5]:  # 显示前5个持仓
                        print(f"   持仓: {pos.get('symbol')}, 数量: {pos.get('volume')}")
            else:
                print("❌ 获取持仓失败")
                
            # 测试市场数据
            try:
                market_data = gm.current(symbols=bot.symbols[0])
                if market_data:
                    print(f"✅ 市场数据获取成功: {market_data[0]}")
                else:
                    print("⚠️  市场数据为空")
            except Exception as e:
                print(f"❌ 市场数据获取失败: {e}")
                
            print("\n✅ 基本功能测试完成")
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
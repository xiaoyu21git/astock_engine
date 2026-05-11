"""
数据获取事件处理器
接收C++ EventBus的事件，获取数据并存储到数据库
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import threading

logger = logging.getLogger(__name__)


class DataFetchHandler:
    """数据获取事件处理器"""
    
    def __init__(self, event_bus=None):
        """
        初始化数据获取处理器
        
        Args:
            event_bus: EventBus实例
        """
        self.event_bus = event_bus
        self.running = False
        self.thread = None
        
        # 数据源管理器
        self.data_sources = {}
        
        # 数据库连接
        self.database = None
        
        # 请求跟踪
        self.active_requests = {}
        
        logger.info("数据获取处理器初始化")
    
    def initialize(self, event_bus) -> bool:
        """
        初始化处理器
        
        Args:
            event_bus: EventBus实例
            
        Returns:
            bool: 初始化是否成功
        """
        try:
            self.event_bus = event_bus
            
            # 订阅数据获取事件
            self.event_bus.subscribe('data.fetch.request', self.handle_fetch_request)
            self.event_bus.subscribe('database.save.request', self.handle_save_request)
            self.event_bus.subscribe('database.load.request', self.handle_load_request)
            
            # 初始化数据源
            self._initialize_data_sources()
            
            # 初始化数据库
            self._initialize_database()
            
            # 启动处理线程
            self.running = True
            self.thread = threading.Thread(target=self._process_loop, daemon=True)
            self.thread.start()
            
            logger.info("数据获取处理器初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"处理器初始化失败: {e}")
            return False
    
    def _initialize_data_sources(self):
        """初始化数据源"""
        try:
            from astock_engine.data.juejin_data_source import JuejinDataSource
            from astock_engine.data.data_provider import AkShareProvider, TushareProvider
            
            # 创建数据源实例
            self.data_sources = {
                'juejin': JuejinDataSource(self.event_bus),
                'akshare': AkShareProvider(),
                'tushare': None  # 需要token
            }
            
            # 初始化掘金数据源
            if isinstance(self.data_sources['juejin'], JuejinDataSource):
                self.data_sources['juejin'].initialize()
            
            logger.info(f"数据源初始化完成: {list(self.data_sources.keys())}")
            
        except Exception as e:
            logger.error(f"数据源初始化失败: {e}")
    
    def _initialize_database(self):
        """初始化数据库连接"""
        try:
            from astock_engine.data.database_wrapper import Database, DatabaseConfig
            
            # 创建数据库配置
            db_config = DatabaseConfig(
                host='127.0.0.1',
                port=3306,
                database='astock_quant',
                username='root',
                password='',
                charset='utf8mb4',
                pool_size=10,
                max_overflow=20
            )
            
            # 创建数据库实例
            self.database = Database(db_config)
            
            # 初始化数据库连接
            if self.database.initialize():
                logger.info("数据库连接初始化完成")
            else:
                logger.error("数据库初始化失败")
                self.database = None
                
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            self.database = None
    
    def handle_fetch_request(self, event):
        """
        处理数据获取请求
        
        Args:
            event: 事件对象
        """
        try:
            # 提取请求数据
            request_data = event.data if hasattr(event, 'data') else {}
            
            data_source = request_data.get('dataSource', 'juejin')
            symbols = request_data.get('symbols', [])
            start_date = request_data.get('startDate', '')
            end_date = request_data.get('endDate', '')
            data_type = request_data.get('dataType', 'daily')
            request_id = request_data.get('requestId', '')
            
            logger.info(f"收到数据获取请求: {request_id}")
            logger.info(f"  数据源: {data_source}, 标的: {symbols}")
            logger.info(f"  日期范围: {start_date} 至 {end_date}, 类型: {data_type}")
            
            # 发布进度事件
            self._publish_progress(request_id, 10, "开始获取数据")
            
            # 异步处理数据获取
            threading.Thread(
                target=self._fetch_data_async,
                args=(request_id, data_source, symbols, start_date, end_date, data_type),
                daemon=True
            ).start()
            
        except Exception as e:
            logger.error(f"处理数据获取请求失败: {e}")
            self._publish_error(request_id, f"请求处理失败: {str(e)}")
    
    def _fetch_data_async(self, request_id, data_source, symbols, start_date, end_date, data_type):
        """异步获取数据"""
        try:
            # 检查数据源
            if data_source not in self.data_sources:
                self._publish_error(request_id, f"不支持的数据源: {data_source}")
                return
            
            source = self.data_sources[data_source]
            
            # 根据数据源类型获取数据
            if data_source == 'juejin':
                self._fetch_from_juejin(request_id, source, symbols, start_date, end_date, data_type)
            elif data_source in ['akshare', 'tushare']:
                self._fetch_from_provider(request_id, source, symbols, start_date, end_date, data_type)
            else:
                self._publish_error(request_id, f"未知的数据源类型: {data_source}")
                
        except Exception as e:
            logger.error(f"异步数据获取失败: {e}")
            self._publish_error(request_id, f"数据获取失败: {str(e)}")
    
    def _fetch_from_juejin(self, request_id, source, symbols, start_date, end_date, data_type):
        """从掘金获取数据"""
        try:
            self._publish_progress(request_id, 20, "连接掘金平台")
            
            # 连接掘金
            if not source.connect():
                self._publish_error(request_id, "连接掘金平台失败")
                return
            
            self._publish_progress(request_id, 30, "订阅市场数据")
            
            # 订阅数据
            if not source.subscribe_market_data(symbols):
                self._publish_error(request_id, "订阅市场数据失败")
                return
            
            # 获取历史数据
            all_data = []
            
            for i, symbol in enumerate(symbols):
                progress = 40 + int(30 * i / len(symbols))
                self._publish_progress(request_id, progress, f"获取 {symbol} 数据")
                
                if data_type == 'daily':
                    # 获取日线数据
                    historical_data = source.get_historical_data(symbol, start_date, end_date)
                    
                    # 转换数据格式
                    for data_point in historical_data:
                        formatted_data = {
                            'symbol': symbol,
                            'date': data_point['date'],
                            'open': data_point['open'],
                            'high': data_point['high'],
                            'low': data_point['low'],
                            'close': data_point['close'],
                            'volume': data_point['volume'],
                            'timestamp': data_point.get('timestamp', ''),
                            'data_type': 'daily',
                            'source': 'juejin'
                        }
                        all_data.append(formatted_data)
                
                elif data_type == 'minute':
                    # 获取分钟数据（模拟）
                    self._publish_progress(request_id, progress + 5, f"获取 {symbol} 分钟数据（模拟）")
                    # 这里应该实现实际的分钟数据获取
                    pass
                
                time.sleep(0.5)  # 避免请求过快
            
            # 停止实时数据
            source.stop_real_time()
            
            # 发布完成事件
            self._publish_complete(request_id, all_data, f"数据获取完成: {len(all_data)}条")
            
            # 自动保存到数据库
            if self.database and all_data:
                self._save_to_database_async(request_id, all_data)
            
        except Exception as e:
            logger.error(f"掘金数据获取失败: {e}")
            self._publish_error(request_id, f"掘金数据获取失败: {str(e)}")
    
    def _fetch_from_provider(self, request_id, provider, symbols, start_date, end_date, data_type):
        """从数据提供者获取数据"""
        try:
            self._publish_progress(request_id, 20, f"从 {type(provider).__name__} 获取数据")
            
            all_data = []
            
            for i, symbol in enumerate(symbols):
                progress = 30 + int(50 * i / len(symbols))
                self._publish_progress(request_id, progress, f"获取 {symbol} 数据")
                
                try:
                    # 获取日线数据
                    df = provider.get_daily_data(symbol, start_date, end_date)
                    
                    if df is not None and not df.empty:
                        # 转换DataFrame为列表
                        for index, row in df.iterrows():
                            formatted_data = {
                                'symbol': symbol,
                                'date': index.strftime('%Y-%m-%d') if hasattr(index, 'strftime') else str(index),
                                'open': float(row.get('open', 0)),
                                'high': float(row.get('high', 0)),
                                'low': float(row.get('low', 0)),
                                'close': float(row.get('close', 0)),
                                'volume': float(row.get('volume', 0)),
                                'data_type': 'daily',
                                'source': type(provider).__name__.lower()
                            }
                            all_data.append(formatted_data)
                    
                    logger.info(f"获取 {symbol} 数据: {len(df) if df is not None else 0}条")
                    
                except Exception as e:
                    logger.error(f"获取 {symbol} 数据失败: {e}")
                    self._publish_progress(request_id, progress, f"获取 {symbol} 数据失败: {str(e)[:50]}")
                
                time.sleep(0.3)  # 避免请求过快
            
            # 发布完成事件
            self._publish_complete(request_id, all_data, f"数据获取完成: {len(all_data)}条")
            
            # 自动保存到数据库
            if self.database and all_data:
                self._save_to_database_async(request_id, all_data)
            
        except Exception as e:
            logger.error(f"数据提供者获取失败: {e}")
            self._publish_error(request_id, f"数据获取失败: {str(e)}")
    
    def handle_save_request(self, event):
        """处理数据库保存请求"""
        try:
            request_data = event.data if hasattr(event, 'data') else {}
            data = request_data.get('data', [])
            request_id = f"save_{int(time.time())}"
            
            if not data:
                self._publish_save_result(request_id, False, "没有数据可保存")
                return
            
            self._save_to_database_async(request_id, data)
            
        except Exception as e:
            logger.error(f"处理保存请求失败: {e}")
            self._publish_save_result("unknown", False, f"保存失败: {str(e)}")
    
    def handle_load_request(self, event):
        """处理数据库加载请求"""
        try:
            request_data = event.data if hasattr(event, 'data') else {}
            symbol = request_data.get('symbol', '')
            start_date = request_data.get('startDate', '')
            end_date = request_data.get('endDate', '')
            data_type = request_data.get('dataType', 'daily')
            request_id = f"load_{int(time.time())}"
            
            if not self.database:
                self._publish_load_result(request_id, False, "数据库未连接", [], 0)
                return
            
            if not symbol:
                self._publish_load_result(request_id, False, "未指定股票代码", [], 0)
                return
            
            # 异步加载数据
            threading.Thread(
                target=self._load_from_database_async,
                args=(request_id, symbol, start_date, end_date, data_type),
                daemon=True
            ).start()
            
        except Exception as e:
            logger.error(f"处理加载请求失败: {e}")
            self._publish_load_result("unknown", False, f"加载失败: {str(e)}", [], 0)
    
    def _save_to_database_async(self, request_id, data):
        """异步保存数据到数据库"""
        try:
            if not self.database:
                self._publish_save_result(request_id, False, "数据库未连接")
                return
            
            self._publish_progress(request_id, 60, "正在保存数据到数据库")
            
            # 保存数据
            saved_count = 0
            for data_point in data:
                try:
                    # 保存日线数据
                    if data_point.get('data_type') == 'daily':
                        trade_date = data_point.get('trade_date') or data_point.get('date', '')
                        turnover = data_point.get('turnover')
                        if turnover is None:
                            turnover = data_point.get('amount')
                        if turnover is None:
                            turnover = data_point.get('volume', 0) * data_point.get('close', 0)

                        daily_bar = {
                            'symbol': data_point.get('symbol', ''),
                            'trade_date': trade_date,
                            'open': data_point.get('open', 0),
                            'high': data_point.get('high', 0),
                            'low': data_point.get('low', 0),
                            'close': data_point.get('close', 0),
                            'pre_close': data_point.get('pre_close', data_point.get('prev_close', 0)),
                            'volume': data_point.get('volume', 0),
                            'turnover': turnover,
                            'change_pct': data_point.get('change_pct', data_point.get('pct_chg', 0)),
                            'change_amt': data_point.get('change_amt', data_point.get('change', 0)),
                            'amplitude': data_point.get('amplitude', 0),
                            'turnover_rate': data_point.get('turnover_rate', 0),
                            'pe_ratio': data_point.get('pe_ratio', data_point.get('pe', 0)),
                            'pb_ratio': data_point.get('pb_ratio', data_point.get('pb', 0)),
                            'market_cap': data_point.get('market_cap', data_point.get('total_market_cap', 0)),
                            'circulating_market_cap': data_point.get('circulating_market_cap', data_point.get('float_market_cap', 0)),
                            'pre_adjust_factor': data_point.get('pre_adjust_factor', 0),
                            'post_adjust_factor': data_point.get('post_adjust_factor', data_point.get('adj_factor', 0)),
                            'data_source': data_point.get('data_source', data_point.get('source', '')),
                            'created_at': data_point.get('created_at', ''),
                            'updated_at': data_point.get('updated_at', '')
                        }
                        # 批量保存更高效，但这里先单个保存
                        self.database.save_daily_bars([daily_bar])
                        saved_count += 1
                    
                    # 保存tick数据
                    elif data_point.get('data_type') == 'tick':
                        # 暂时不支持tick数据
                        logger.warning("Tick数据保存暂未实现")
                    
                except Exception as e:
                    logger.warning(f"保存数据点失败: {e}")
            
            self._publish_save_result(request_id, True, f"保存成功: {saved_count}条数据")
            
        except Exception as e:
            logger.error(f"数据库保存失败: {e}")
            self._publish_save_result(request_id, False, f"保存失败: {str(e)}")
    
    def _load_from_database_async(self, request_id, symbol, start_date, end_date, data_type):
        """异步从数据库加载数据"""
        try:
            if not self.database:
                self._publish_load_result(request_id, False, "数据库未连接", [], 0)
                return
            
            self._publish_progress(request_id, 50, "正在从数据库加载数据")
            
            # 加载数据
            data = []
            
            if data_type == 'daily':
                # 使用正确的数据库方法
                daily_bars = self.database.get_daily_bars(symbol, start_date, end_date)
                # 转换为标准格式
                for bar in daily_bars:
                    data.append({
                        'symbol': bar.get('symbol', symbol),
                        'date': bar.get('trade_date', ''),
                        'open': bar.get('open', 0),
                        'high': bar.get('high', 0),
                        'low': bar.get('low', 0),
                        'close': bar.get('close', 0),
                        'volume': bar.get('volume', 0),
                        'data_type': 'daily',
                        'source': 'database'
                    })
            elif data_type == 'tick':
                # 暂时不支持tick数据
                logger.warning("Tick数据加载暂未实现")
            
            self._publish_load_result(request_id, True, f"加载成功", data, len(data))
            
        except Exception as e:
            logger.error(f"数据库加载失败: {e}")
            self._publish_load_result(request_id, False, f"加载失败: {str(e)}", [], 0)
    
    def _publish_progress(self, request_id, progress, message):
        """发布进度事件"""
        try:
            if self.event_bus:
                self.event_bus.publish('data.fetch.progress', {
                    'requestId': request_id,
                    'progress': progress,
                    'message': message,
                    'timestamp': datetime.now().isoformat()
                })
        except Exception as e:
            logger.error(f"发布进度事件失败: {e}")
    
    def _publish_complete(self, request_id, data, message):
        """发布完成事件"""
        try:
            if self.event_bus:
                self.event_bus.publish('data.fetch.complete', {
                    'requestId': request_id,
                    'data': data,
                    'count': len(data),
                    'message': message,
                    'timestamp': datetime.now().isoformat()
                })
        except Exception as e:
            logger.error(f"发布完成事件失败: {e}")
    
    def _publish_error(self, request_id, error_message):
        """发布错误事件"""
        try:
            if self.event_bus:
                self.event_bus.publish('data.fetch.error', {
                    'requestId': request_id,
                    'error': error_message,
                    'timestamp': datetime.now().isoformat()
                })
        except Exception as e:
            logger.error(f"发布错误事件失败: {e}")
    
    def _publish_save_result(self, request_id, success, message):
        """发布保存结果事件"""
        try:
            if self.event_bus:
                self.event_bus.publish('database.save.result', {
                    'requestId': request_id,
                    'success': success,
                    'message': message,
                    'timestamp': datetime.now().isoformat()
                })
        except Exception as e:
            logger.error(f"发布保存结果事件失败: {e}")
    
    def _publish_load_result(self, request_id, success, message, data, count):
        """发布加载结果事件"""
        try:
            if self.event_bus:
                self.event_bus.publish('database.load.result', {
                    'requestId': request_id,
                    'success': success,
                    'message': message,
                    'data': data,
                    'count': count,
                    'timestamp': datetime.now().isoformat()
                })
        except Exception as e:
            logger.error(f"发布加载结果事件失败: {e}")
    
    def _process_loop(self):
        """处理循环"""
        logger.info("数据获取处理器循环启动")
        
        while self.running:
            try:
                # 定期清理过期的请求
                current_time = time.time()
                expired_requests = []
                
                for req_id, req_time in list(self.active_requests.items()):
                    if current_time - req_time > 3600:  # 1小时过期
                        expired_requests.append(req_id)
                
                for req_id in expired_requests:
                    del self.active_requests[req_id]
                
                time.sleep(5.0)  # 5秒检查一次
                
            except Exception as e:
                logger.error(f"处理循环错误: {e}")
                time.sleep(10.0)
        
        logger.info("数据获取处理器循环停止")
    
    def shutdown(self):
        """关闭处理器"""
        try:
            self.running = False
            
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=2.0)
            
            # 关闭数据源
            for source_name, source in self.data_sources.items():
                if hasattr(source, 'shutdown'):
                    try:
                        source.shutdown()
                    except Exception as e:
                        logger.warning(f"关闭数据源 {source_name} 失败: {e}")
            
            # 关闭数据库连接
            if self.database and hasattr(self.database, 'close'):
                try:
                    self.database.close()
                except Exception as e:
                    logger.warning(f"关闭数据库连接失败: {e}")
            
            logger.info("数据获取处理器已关闭")
            
        except Exception as e:
            logger.error(f"关闭处理器失败: {e}")

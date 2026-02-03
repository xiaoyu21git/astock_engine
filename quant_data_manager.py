"""
quant_data_manager.py

统一管理量化数据源的接入、账号登录、数据源切换。
支持多平台（如聚宽、掘金、米筐、模拟等）一键切换。
"""

from typing import Optional, Dict, Any

class QuantDataManager:
        def subscribe_globalstate_events(self, eventbus=None):
            """
            订阅 C++ 侧 globalstate.changed 事件，实现 Python 层自动同步。
            eventbus: 可选，指定 EventBus 实例，否则用全局 EventBus。
            """
            if eventbus is None:
                try:
                    from astock_engine.core.eventbus_simple import get_global_bus
                    eventbus = get_global_bus()
                except ImportError:
                    print("[QuantDataManager] EventBus 不可用，无法同步 globalstate 事件")
                    return

            def on_globalstate_changed(event):
                key = None
                value = None
                if hasattr(event, 'data') and isinstance(event.data, dict):
                    key = event.data.get('key')
                    value = event.data.get('value')
                elif hasattr(event, 'attributes'):
                    key = event.attributes.get('key')
                    value = event.attributes.get('value')
                if key:
                    print(f"[QuantDataManager] 状态同步: {key} = {value}")
                    # 自动同步到 Python 层变量
                    setattr(self, key, value)
                    # 聚宽相关状态同步
                    if key == 'token':
                        # token 变更时可自动触发登录/登出等逻辑
                        self.jqToken = value
                    elif key == 'accountId':
                        self.jqAccountId = value
                    elif key == 'jqConnected':
                        self.jqConnected = bool(value)
                    elif key == 'jqConnecting':
                        self.jqConnecting = bool(value)

            # 支持字符串事件类型
            eventbus.subscribe('globalstate.changed', on_globalstate_changed)
    """
    统一管理主流量化数据平台的数据接入、账号登录、数据源切换。
    支持：聚宽（JoinQuant）、掘金（MyQuant）、米筐（RiceQuant）、TuShare、模拟（Simulated）等。
    """
    def __init__(self):
        self.current_source = None
        self.current_account = None
        self.sources = {}

        # 内置主流平台注册模板
        self._register_builtin_sources()

    def _register_builtin_sources(self):
        # 聚宽 JoinQuant
        try:
            import jqdatasdk
            import os
            def jq_login(username=None, password=None):
                # 优先用环境变量，否则交互式输入
                if not username:
                    username = os.getenv('JQ_USERNAME')
                if not password:
                    password = os.getenv('JQ_PASSWORD')
                if not username:
                    username = input('请输入聚宽账号: ')
                if not password:
                    try:
                        import getpass
                        password = getpass.getpass('请输入聚宽密码: ')
                    except Exception:
                        password = input('请输入聚宽密码: ')
                jqdatasdk.auth(username, password)
                return True
            def jq_fetch(symbol, start_date, end_date, freq='1d'):
                return jqdatasdk.get_price(symbol, start_date, end_date, frequency=freq)
            def jq_logout():
                jqdatasdk.logout()
            self.register_source('joinquant', jq_login, jq_fetch, jq_logout)
        except ImportError:
            pass

        # 掘金 MyQuant（需自定义实现）
        try:
            from astock_engine.broker.myquant_broker import MyQuantBroker
            def myquant_login(token=None, account_id=None):
                global _myquant_broker
                _myquant_broker = MyQuantBroker(token=token, account_id=account_id)
                return True
            def myquant_fetch(symbol, start_date=None, end_date=None, freq='1d'):
                # 需根据实际接口实现
                return _myquant_broker  # 占位
            def myquant_logout():
                pass
            self.register_source('myquant', myquant_login, myquant_fetch, myquant_logout)
        except ImportError:
            pass

        # 米筐 RiceQuant（需安装 ricequant）
        try:
            import rqdatac
            def ricequant_login(username, password):
                rqdatac.init(username, password)
                return True
            def ricequant_fetch(symbol, start_date, end_date, freq='1d'):
                return rqdatac.get_price(symbol, start_date, end_date, frequency=freq)
            def ricequant_logout():
                rqdatac.close()
            self.register_source('ricequant', ricequant_login, ricequant_fetch, ricequant_logout)
        except ImportError:
            pass

        # TuShare
        try:
            import tushare as ts
            def tushare_login(token):
                global _ts_pro
                _ts_pro = ts.pro_api(token)
                return True
            def tushare_fetch(symbol, start_date, end_date, freq='D'):
                return _ts_pro.daily(ts_code=symbol, start_date=start_date, end_date=end_date)
            def tushare_logout():
                pass
            self.register_source('tushare', tushare_login, tushare_fetch, tushare_logout)
        except ImportError:
            pass

        # 模拟 Simulated（需自定义实现）
        try:
            from astock_engine.broker.simulated_broker import SimulatedBroker
            from astock_engine.core import EventBus
            def simulated_login(initial_cash=1_000_000):
                global _sim_broker
                _sim_broker = SimulatedBroker(EventBus(), initial_cash=initial_cash)
                return True
            def simulated_fetch(symbol, start_date=None, end_date=None, freq='1d'):
                # 需根据实际接口实现
                return _sim_broker  # 占位
            def simulated_logout():
                pass
            self.register_source('simulated', simulated_login, simulated_fetch, simulated_logout)
        except ImportError:
            pass

    def register_source(self, name: str, login_func, fetch_func, logout_func=None):
        self.sources[name] = {
            'login': login_func,
            'fetch': fetch_func,
            'logout': logout_func,
        }

    def login(self, name: str, **kwargs) -> bool:
        if name not in self.sources:
            raise ValueError(f"数据源 {name} 未注册")
        ok = self.sources[name]['login'](**kwargs)
        if ok:
            self.current_source = name
            self.current_account = kwargs
        return ok

    def fetch(self, **kwargs) -> Any:
        if not self.current_source:
            raise RuntimeError("未登录任何数据源")
        return self.sources[self.current_source]['fetch'](**kwargs)

    def logout(self):
        if self.current_source and self.sources[self.current_source]['logout']:
            self.sources[self.current_source]['logout']()
        self.current_source = None
        self.current_account = None

    def switch(self, name: str, **kwargs) -> bool:
        self.logout()
        return self.login(name, **kwargs)

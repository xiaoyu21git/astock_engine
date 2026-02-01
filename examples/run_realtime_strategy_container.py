"""
通用实时策略容器示例

目标：
- 使用 EventBus 驱动一个通用的实时执行容器
- 通过策略插件 ID 选择具体策略（如 ma_crossover、volume_price、macd_strategy 等）
- 模拟实时行情流入 -> 策略发出信号 -> 模拟下单/成交

运行方式（在项目根目录）：

    G:/C++/AStockQuantEngine/.venv/Scripts/python.exe astock_engine/examples/run_realtime_strategy_container.py

可以通过修改 DEFAULT_CONFIG['strategy_id'] 切换不同插件策略。
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

import numpy as np
import pandas as pd

# 将项目根目录加入路径，便于作为脚本直接运行
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from astock_engine.core import EventBus, EventType, Event
from astock_engine.strategies.plugin_manager import StrategyPluginManager
from astock_engine.broker import (
    SimulatedBroker,
    MyQuantBroker,
    OrderRequest,
    OrderSide,
    OrderType,
)
from astock_engine.risk.risk_manager import RiskManager, RiskConfig
from astock_engine.data.providers import NewsDataProvider
from astock_engine.factors.industry_sentiment import update_from_news_row
from tools.live_account_snapshot import build_snapshot as build_account_snapshot


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


DEFAULT_CONFIG: Dict[str, Any] = {
    # Broker 类型: "simulated" / "myquant"
    "broker": "simulated",
    # 使用的插件策略 ID（对应 strategies/plugins 下目录名）
    # 默认使用一个会根据行情生成信号的策略插件
    "strategy_id": "intraday_arb",
    # 模拟标的列表
    "symbols": ["000001.SZ", "600000.SH", "000002.SZ"],
    # 模拟天数
    "days": 120,
    # 推送间隔（秒）——可适当调大便于观察日志
    "tick_interval": 0.05,
    # 订单路由："sim" 使用本地模拟券商，"myquant" 通过掘金 MyQuant 下单（仿真/实盘）
    "broker_mode": "myquant",
    # 行情来源："mock" 使用本地随机生成行情，"myquant" 使用掘金真实行情
    "market_source": "myquant",
    # 是否启用舆情/新闻流（通过 NewsDataProvider 轮询 + EventBus.NEWS 推送）
    "enable_news_feed": False,
    # 新闻轮询间隔（秒）
    "news_poll_interval": 5.0,
    # 账户快照写入间隔（秒），仅在 broker_mode="myquant" 时生效
    "account_snapshot_interval": 10.0,
}

# 是否在 myquant 模式下用券商账户资金/持仓对齐风控。
# 目前这条线不再使用，统一采用固定初始资金做风控。
ALIGN_RISK_WITH_BROKER = False

# 是否在启动容器时发送一条测试信号，用于联调下单/回报链路。
# 注意：在 myquant 模式下这会真实向掘金账户发一笔小单，请确认账户环境（建议仿真）。
ENABLE_TEST_SIGNAL = False
TEST_SIGNAL_CONFIG: Dict[str, Any] = {
    "symbol": "000001.SZ",
    "direction": 1,  # 1=BUY, -1=SELL
    "strength": 1.0,
    # 对 myquant 模式下的市价单，这里的 price 仅用于风控估价，不作为实际委托价
    "price": 10.0,
    "reason": "test_manual_signal",
}


class AccountSnapshotScheduler:
    """在后台定期将 MyQuantBroker 的账户资金/持仓快照写入 JSON 文件。

    这样 UI 只需要读取 data/live_account_snapshot.json 即可与掘金账户对齐。
    """

    def __init__(self, broker: MyQuantBroker, interval: float = 10.0):
        self.broker = broker
        self.interval = max(float(interval), 1.0)
        self._stopped = False
        self._thread = None

        # 快照输出文件位置：仓库根目录下的 data/live_account_snapshot.json
        self._repo_root = Path(__file__).resolve().parents[2]
        self._out_dir = self._repo_root / "data"
        self._out_file = self._out_dir / "live_account_snapshot.json"

    def start(self) -> None:
        import threading

        self._stopped = False
        self._thread = threading.Thread(target=self._run, name="AccountSnapshotScheduler", daemon=True)
        self._thread.start()
        logger.info(
            "AccountSnapshotScheduler 已启动，间隔=%.1fs, 输出=%s",
            self.interval,
            self._out_file,
        )

    def stop(self) -> None:
        self._stopped = True

    def _run(self) -> None:
        import json

        try:
            self._out_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        while not self._stopped:
            try:
                snap = build_account_snapshot(self.broker)
                tmp = self._out_file.with_suffix(".json.tmp")
                with tmp.open("w", encoding="utf-8") as f:
                    json.dump(snap, f, ensure_ascii=False, indent=2)
                tmp.replace(self._out_file)
            except Exception as exc:  # pragma: no cover - 防御性
                logger.warning("AccountSnapshotScheduler 写入账户快照失败: %s", exc)

            time.sleep(self.interval)


class MockRealtimeDataFeed:
    """简单的实时行情推送模拟器

    - 预先生成一段 K 线数据
    - 按日期顺序，逐天将当日每个标的的 close/volume 通过 EventBus 推送出去
    """

    def __init__(self, bus: EventBus, symbols: List[str], days: int, interval: float):
        self.bus = bus
        self.symbols = symbols
        self.days = days
        self.interval = interval
        self._data = self._generate_mock_data()

    def _generate_mock_data(self) -> pd.DataFrame:
        dates = pd.date_range(end=datetime.now(), periods=self.days, freq="D")
        rows = []
        for symbol in self.symbols:
            base = float(np.random.uniform(10, 50))
            trend = float(np.random.choice([-0.5, 0.0, 0.5]))
            prices = [base]
            for _ in range(1, self.days):
                change = float(np.random.normal(trend, 1.5))
                new_price = max(prices[-1] * (1 + change / 100.0), base * 0.5)
                prices.append(new_price)
            for dt, price in zip(dates, prices):
                rows.append(
                    {
                        "date": dt,
                        "symbol": symbol,
                        "close": float(price),
                        "volume": int(np.random.randint(500000, 5000000)),
                    }
                )
        df = pd.DataFrame(rows)
        logger.info("生成实时模拟行情: %d 条记录", len(df))
        return df

    def run(self):
        dates = sorted(self._data["date"].unique())
        logger.info("开始实时推送行情，共 %d 天", len(dates))

        for idx, dt in enumerate(dates, start=1):
            daily = self._data[self._data["date"] == dt]
            logger.info("\n%s", "=" * 60)
            logger.info("日期: %s (%d/%d)", dt.strftime("%Y-%m-%d"), idx, len(dates))
            logger.info("%s", "=" * 60)

            for _, row in daily.iterrows():
                evt = Event(
                    type=EventType.MARKET_DATA,
                    data={
                        "symbol": row["symbol"],
                        "close": float(row["close"]),
                        "volume": int(row["volume"]),
                        "timestamp": dt,
                    },
                    timestamp=dt,
                )
                self.bus.publish(evt)

            time.sleep(self.interval)

        logger.info("实时行情推送结束")


class SimpleOrderExecutor:
    """兼容旧示例的别名。

    为了不破坏已有使用习惯，这里保留 SimpleOrderExecutor 名称，
    但内部根据配置选择具体 Broker 实现。
    """

    def __init__(self, bus: EventBus, mode: str = "sim", broker: MyQuantBroker | None = None):
        self.bus = bus
        self.mode = (mode or "sim").lower()

        if self.mode == "myquant":
            # MyQuantBroker 内部使用 gm.api，下单将发送到掘金账户（仿真/实盘）
            # 允许外部传入已初始化的 broker，便于与风控等组件共享账户状态
            self.broker = broker or MyQuantBroker()

            # 为 myquant 模式订阅策略/下单事件，并转发到 Broker
            if hasattr(EventType, "STRATEGY_SIGNAL"):
                self.bus.subscribe(EventType.STRATEGY_SIGNAL, self._on_strategy_signal)
            if hasattr(EventType, "ORDER"):
                self.bus.subscribe(EventType.ORDER, self._on_order_event)
            try:
                self.bus.subscribe("signal", self._on_generic_signal)
                self.bus.subscribe("place_order", self._on_place_order)
            except Exception:
                # 某些 EventBus 实现可能不支持字符串 topic
                pass
        else:
            # 默认使用本地模拟券商（其内部自行订阅 EventBus）
            self.broker = SimulatedBroker(bus)

    # === 针对 myquant 模式的事件处理器 ===

    def _on_strategy_signal(self, event: Event):
        data = getattr(event, "data", {}) or {}
        symbol = data.get("symbol")
        direction = data.get("direction")
        price = data.get("price")
        logger.info("[STRATEGY_SIGNAL] %s dir=%s price=%s", symbol, direction, price)

    def _on_order_event(self, event: Event):
        data = getattr(event, "data", {}) or {}
        symbol = data.get("symbol")
        side = str(data.get("side", "BUY")).upper()
        qty = int(data.get("quantity", 0) or 0)
        price = float(data.get("price", 0.0) or 0.0)
        logger.info("[ORDER] %s %s x%s @ %s", side, symbol, qty, price)

        self._submit_broker_order(symbol, side, qty, price)

    def _on_generic_signal(self, event: Event):
        data = getattr(event, "data", {}) or {}
        logger.info("[signal] %s", data)

    def _on_place_order(self, event: Event):
        data = getattr(event, "data", {}) or {}
        symbol = data.get("symbol")
        side = str(data.get("side", "BUY")).upper()
        qty = int(data.get("quantity", 0) or 0)
        price = float(data.get("price", 0.0) or 0.0)
        logger.info("[place_order] %s %s x%s @ %s", side, symbol, qty, price)

        self._submit_broker_order(symbol, side, qty, price)

    def _submit_broker_order(self, symbol: Any, side: str, qty: int, price: float) -> None:
        if not symbol or qty <= 0:
            return

        side_enum = OrderSide.BUY if side == "BUY" else OrderSide.SELL
        # myquant 模式下一律使用市价单，由券商按真实行情成交
        if self.mode == "myquant":
            order_type = OrderType.MARKET
            order_price: float | None = None
        else:
            # 模拟券商可继续使用限价/市价逻辑
            if price > 0:
                order_type = OrderType.LIMIT
                order_price = price
            else:
                order_type = OrderType.MARKET
                order_price = None

        req = OrderRequest(
            symbol=str(symbol),
            side=side_enum,
            quantity=qty,
            price=order_price,
            order_type=order_type,
        )

        try:
            status = self.broker.place_order(req)
            # 将订单结果和简单成交回报回填到 EventBus，方便策略/监控订阅
            try:
                resp_evt = Event(
                    type=EventType.ORDER_RESPONSE,
                    data={
                        "order_id": status.order_id,
                        "symbol": str(symbol),
                        "side": side,
                        "action": side,
                        "quantity": int(status.filled_quantity or qty),
                        "price": float(status.avg_price or (price or 0.0)),
                        "avg_price": float(status.avg_price or (price or 0.0)),
                        "status": status.status,
                        "source": "MyQuantBroker" if self.mode == "myquant" else "SimulatedBroker",
                        "timestamp": time.time(),
                    },
                )
                self.bus.publish(resp_evt)

                if status.filled_quantity:
                    trade_evt = Event(
                        type=EventType.TRADE,
                        data={
                            "order_id": status.order_id,
                            "symbol": str(symbol),
                            "side": side,
                            "quantity": int(status.filled_quantity),
                            "price": float(status.avg_price or (price or 0.0)),
                            "source": "MyQuantBroker" if self.mode == "myquant" else "SimulatedBroker",
                            "timestamp": time.time(),
                        },
                    )
                    self.bus.publish(trade_evt)
            except Exception:
                # 回推事件失败不影响下单主流程
                pass
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("[SimpleOrderExecutor] 下单失败: %s", exc)


class RealtimeFactorLogger:
    """订阅实时行情，在本地累积 K 线并计算情绪 / 政策因子后输出日志。

    当前主要用于观测 VolumePrice 策略链路中：
    - market_sentiment（全市场情绪）
    - policy_score（题材政策因子）
    随时间的变化情况。
    """

    def __init__(self, bus: EventBus, strategy: Any):  # type: ignore[valid-type]
        self.bus = bus
        # 对 volume_price 插件来说，核心策略在 core_strategy 上
        self.core_strategy = getattr(strategy, "core_strategy", None)
        if self.core_strategy is None:
            logger.warning("RealtimeFactorLogger: 策略对象不包含 core_strategy，跳过因子日志功能")
            return

        self.history: Dict[str, pd.DataFrame] = {}
        # 仅在存在 MARKET_DATA 枚举时订阅
        try:
            self.bus.subscribe(EventType.MARKET_DATA, self._on_market_data)
            logger.info("RealtimeFactorLogger 已订阅 MARKET_DATA 事件")
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("RealtimeFactorLogger 订阅 MARKET_DATA 失败: %s", exc)

    def _on_market_data(self, event: Event):
        if self.core_strategy is None:
            return

        data = getattr(event, "data", {}) or {}
        symbol = data.get("symbol")
        ts = data.get("timestamp")
        close = data.get("close")
        volume = data.get("volume", 0)

        if symbol is None or ts is None or close is None:
            return

        ts = pd.to_datetime(ts)

        # 为满足指标计算接口，简单构造 OHLCV，其中 O/H/L 近似等于收盘价
        row = {
            "open": float(close),
            "high": float(close),
            "low": float(close),
            "close": float(close),
            "volume": int(volume),
        }

        df = self.history.get(symbol)
        if df is None:
            df = pd.DataFrame([row], index=[ts])
        else:
            df.loc[ts] = row
            df.sort_index(inplace=True)
        self.history[symbol] = df

        # 构造 {symbol: df} 结构并调用核心策略的指标计算
        data_dict: Dict[str, pd.DataFrame] = {s: d for s, d in self.history.items()}
        try:
            data_dict = self.core_strategy.calculate_indicators(data_dict)
        except Exception as exc:  # pragma: no cover - 日志观察用
            logger.warning("RealtimeFactorLogger 计算因子失败: %s", exc)
            return

        cur_df = data_dict.get(symbol)
        if cur_df is None or cur_df.empty:
            return

        latest = cur_df.iloc[-1]

        def _fmt(name: str) -> str:
            if name not in latest or pd.isna(latest[name]):
                return "NA"
            try:
                return f"{float(latest[name]):.3f}"
            except Exception:
                return "NA"

        market_sent = _fmt("market_sentiment")
        policy_score = _fmt("policy_score")

        logger.info(
            "[FACTORS] %s %s close=%.2f sentiment=%s policy=%s",
            symbol,
            ts.strftime("%Y-%m-%d"),
            float(close),
            market_sent,
            policy_score,
        )


class RealtimeRiskMonitor:
    """基于实时行情更新风控持仓价格，并定期输出账户风险状态。

    - 订阅 MARKET_DATA，将最新收盘价同步到 RiskManager.positions
    - 每隔 log_interval 秒调用一次 risk_manager.log_status()
    """

    def __init__(self, bus: EventBus, risk_manager: RiskManager, log_interval: float = 60.0):
        self.bus = bus
        self.risk_manager = risk_manager
        self.log_interval = max(float(log_interval), 1.0)
        self._last_log_ts: float = 0.0

        try:
            self.bus.subscribe(EventType.MARKET_DATA, self._on_market_data)
            logger.info("RealtimeRiskMonitor 已订阅 MARKET_DATA 事件，用于实时更新风控价格和账户状态")
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("RealtimeRiskMonitor 订阅 MARKET_DATA 失败: %s", exc)

    def _on_market_data(self, event: Event):
        data = getattr(event, "data", {}) or {}
        symbol = data.get("symbol")
        price = data.get("close")

        if not symbol or price is None:
            return

        try:
            px = float(price)
        except Exception:
            return

        # 将最新行情价同步到风控持仓，用于计算仓位、市值、回撤等
        try:
            self.risk_manager.update_position_price(str(symbol), px)
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("RealtimeRiskMonitor 更新持仓价格失败: %s", exc)
            return

        # 简单的时间节流：每 log_interval 秒输出一次总体风控状态
        now_ts = time.time()
        if now_ts - self._last_log_ts >= self.log_interval:
            self._last_log_ts = now_ts
            try:
                self.risk_manager.log_status()
            except Exception as exc:  # pragma: no cover - 防御性
                logger.warning("RealtimeRiskMonitor 输出风控状态失败: %s", exc)


class RealtimeNewsFeed:
    """基于 NewsDataProvider 的实时新闻/舆情推送桥接。

    - 使用 akshare 轮询财经快讯；
    - 对标题做简单情感分析；
    - 将结果以 EventType.NEWS 事件形式发布到 EventBus。
    """

    def __init__(
        self,
        bus: EventBus,
        symbols: List[str] | None = None,
        interval: float = 5.0,
    ):
        self.bus = bus
        self.symbols = symbols or []
        self._provider = NewsDataProvider(config={"subscribe_interval": interval})

        try:
            ok = self._provider.initialize()
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("RealtimeNewsFeed 初始化 NewsDataProvider 失败: %s", exc)
            ok = False

        if not ok:
            logger.warning("RealtimeNewsFeed 未能初始化 NewsDataProvider，将不启用新闻流")
            self._provider = None  # type: ignore[assignment]
            return

        try:
            self._provider.subscribe(self.symbols, self._on_news)
            logger.info(
                "RealtimeNewsFeed 已启动，symbols=%s interval=%.2fs",
                ",".join(self.symbols) if self.symbols else "*",
                float(interval),
            )
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("RealtimeNewsFeed 订阅新闻流失败: %s", exc)

    def _on_news(self, symbol: str, row: Dict[str, Any], ts: float | datetime):
        if self._provider is None:
            return

        # 统一时间戳
        if isinstance(ts, (int, float)):
            publish_ts = datetime.fromtimestamp(ts)
        else:
            publish_ts = ts

        title = (
            row.get("title")
            or row.get("标题")
            or row.get("消息标题")
            or ""
        )
        source = row.get("source") or row.get("文章来源") or ""
        url = row.get("url") or row.get("网址") or ""

        # 文本用于情感分析：优先标题，其次简要内容
        text_for_sent = str(title) + " " + str(row.get("content") or "")
        try:
            sent = self._provider.analyze_sentiment(text_for_sent)
        except Exception:
            sent = {"sentiment": "neutral", "score": 0.0}

        # 将情感得分同步到全局行业 / 题材舆情状态
        try:
            update_from_news_row(symbol=str(symbol or ""), sentiment_score=float(sent.get("score", 0.0) or 0.0), ts=publish_ts)
        except Exception:
            pass

        evt = Event(
            type=EventType.NEWS,
            data={
                "symbol": symbol or "",
                "title": str(title),
                "source": str(source),
                "url": str(url),
                "publish_time": publish_ts,
                "sentiment": sent.get("sentiment", "neutral"),
                "sentiment_score": float(sent.get("score", 0.0) or 0.0),
                "raw": row,
            },
            timestamp=publish_ts,
        )

        try:
            self.bus.publish(evt)
            logger.info(
                "[NEWS] %s %s sentiment=%s score=%.2f",
                symbol or "*",
                str(title)[:60],
                sent.get("sentiment", "neutral"),
                float(sent.get("score", 0.0) or 0.0),
            )
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("RealtimeNewsFeed 发布 NEWS 事件失败: %s", exc)

    def close(self) -> None:
        try:
            if self._provider is not None:
                self._provider.unsubscribe(self.symbols)
                self._provider.close()
        except Exception:
            pass


class SignalToOrderRouter:
    """将策略发出的 SIGNAL/STRATEGY_SIGNAL 事件转换为下单事件。

    - 订阅 EventType.SIGNAL / EventType.STRATEGY_SIGNAL 以及字符串 "signal"；
    - 基于 direction>0/<0 生成 BUY/SELL 方向的 ORDER 事件；
    - 数量采用固定基础手数，可按需要扩展为风控/资金管理逻辑。
    """

    def __init__(
        self,
        bus: EventBus,
        base_quantity: int = 100,
        enable_risk: bool = True,
        risk_initial_capital: float = 1_000_000.0,
        risk_config: RiskConfig | None = None,
        broker: MyQuantBroker | None = None,
    ):
        self.bus = bus
        self.base_quantity = max(int(base_quantity), 1)
        self.risk_manager: RiskManager | None = None

        if enable_risk:
            self.risk_manager = RiskManager(risk_config)
            # 若提供了券商对象（myquant 模式），尝试用真实账户资金/持仓对齐风控状态
            if broker is not None:
                try:
                    snapshot = getattr(broker, "get_account_snapshot", broker.query_account)() or {}
                    # 规范化接口优先：total_asset 字段不存在时回退到旧结构
                    if "total_asset" in snapshot:
                        total_asset = float(snapshot.get("total_asset") or 0.0)
                    else:
                        total_asset = float(snapshot.get("asset") or 0.0) or float(snapshot.get("nav") or 0.0) or float(snapshot.get("cash") or 0.0)

                    init_capital = total_asset if total_asset > 0 else float(risk_initial_capital)
                except Exception:
                    init_capital = float(risk_initial_capital)

                self.risk_manager.initialize(init_capital)
                logger.info(
                    "[SignalToOrderRouter] 风控初始化资金=%.2f (券商总资产=%.2f)",
                    init_capital,
                    total_asset if 'total_asset' in locals() else -1.0,
                )

                # 对齐已有持仓到风控，用于半实盘/接盘运行
                try:
                    # 优先使用规范化持仓接口，便于对齐和调整
                    get_pos = getattr(broker, "get_normalized_positions", None)
                    if callable(get_pos):
                        positions_iter = get_pos()  # type: ignore[assignment]
                    else:
                        positions_payload = broker.query_positions() or {}
                        positions_iter = positions_payload.get("positions") or []

                    synced_count = 0
                    for pos in positions_iter:
                        if not isinstance(pos, dict):
                            continue

                        symbol = str(pos.get("symbol") or "")
                        try:
                            qty = int(pos.get("quantity") or pos.get("volume") or pos.get("qty") or 0)
                            price = float(pos.get("price") or pos.get("vwap") or pos.get("cost_price") or 0.0)
                        except Exception:
                            continue

                        if qty <= 0 or price <= 0:
                            continue

                        entry_time = datetime.now()
                        try:
                            ts_raw = pos.get("entry_time") or pos.get("updated_at") or pos.get("created_at")
                            if ts_raw:
                                entry_time = pd.to_datetime(ts_raw)
                        except Exception:
                            pass

                        self.risk_manager.add_position(symbol, qty, price, entry_time)
                        synced_count += 1

                    logger.info(
                        "[SignalToOrderRouter] 已从券商同步 %d 条持仓到风控",
                        synced_count,
                    )
                except Exception as exc:  # pragma: no cover - 防御性
                    logger.warning("[SignalToOrderRouter] 同步券商持仓到风控失败: %s", exc)
            else:
                # 无外部券商对象时，退回到固定初始资金配置
                # 这里的 initial_capital 与真实账户可能不完全一致，
                # 主要用于控制相对仓位和持仓数量的基础风控。
                init_capital = float(risk_initial_capital)
                self.risk_manager.initialize(init_capital)
                logger.info(
                    "[SignalToOrderRouter] 风控使用固定初始资金=%.2f (无外部券商)",
                    init_capital,
                )

        try:
            if hasattr(EventType, "SIGNAL"):
                self.bus.subscribe(EventType.SIGNAL, self._on_signal_event)
            if hasattr(EventType, "STRATEGY_SIGNAL"):
                self.bus.subscribe(EventType.STRATEGY_SIGNAL, self._on_signal_event)
            # 兼容字符串 topic 的信号
            self.bus.subscribe("signal", self._on_signal_event)
            logger.info("SignalToOrderRouter 已订阅 SIGNAL/STRATEGY_SIGNAL 事件")
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("SignalToOrderRouter 订阅失败: %s", exc)

    def _on_signal_event(self, event: Event):
        data = getattr(event, "data", {}) or {}
        symbol = data.get("symbol")
        direction = data.get("direction")
        price = data.get("price", 0.0)
        strength = float(data.get("strength", 1.0) or 1.0)
        ts = data.get("timestamp") or datetime.now()

        if not symbol or not isinstance(direction, (int, float)):
            return

        direction_val = 1 if direction > 0 else -1 if direction < 0 else 0
        if direction_val == 0:
            return

        side = "BUY" if direction_val > 0 else "SELL"
        # 根据强度简单缩放基础手数，至少为 1 手
        qty = max(int(self.base_quantity * abs(strength)), 1)

        # === 基础风控：在生成 ORDER 之前做开/平仓检查 ===
        if self.risk_manager is not None:
            # 使用信号中的价格近似作为下单价格基准
            try:
                px = float(price or 0.0)
            except Exception:
                px = 0.0

            # 没有价格很难评估仓位，这里保守直接放行
            if px <= 0:
                logger.warning(
                    "[SignalToOrderRouter] 风控: %s 缺少价格信息，跳过风控直接下单",
                    symbol,
                )
            else:
                if side == "BUY":
                    allowed, reason = self.risk_manager.check_open_order(symbol, qty, px)
                    if not allowed:
                        logger.info(
                            "[SignalToOrderRouter] 风控拒绝开仓: %s x%s @ %.4f, 原因=%s",
                            symbol,
                            qty,
                            px,
                            reason,
                        )
                        return
                    # 假设信号对应的委托能够成交，用于更新风控内部头寸
                    ts_dt = data.get("timestamp") or datetime.now()
                    try:
                        # pandas.Timestamp 也兼容
                        ts_dt = pd.to_datetime(ts_dt)
                    except Exception:
                        pass
                    self.risk_manager.add_position(symbol, qty, px, ts_dt)
                else:  # SELL 视为平仓信号
                    allowed, reason = self.risk_manager.check_close_order(symbol)
                    if not allowed:
                        logger.info(
                            "[SignalToOrderRouter] 风控拒绝平仓: %s x%s, 原因=%s",
                            symbol,
                            qty,
                            reason,
                        )
                        return
                    # 使用信号价格作为平仓价更新内部头寸
                    self.risk_manager.remove_position(symbol, px)

        order_evt = Event(
            type=EventType.ORDER,
            data={
                "symbol": symbol,
                "side": side,
                "quantity": qty,
                "price": float(price or 0.0),
                "reason": data.get("reason", "signal_router"),
                "source": "SignalToOrderRouter",
            },
            timestamp=ts,
        )

        try:
            self.bus.publish(order_evt)
            logger.info(
                "[SignalToOrderRouter] %s %s x%s @ %s (reason=%s)",
                side,
                symbol,
                qty,
                price,
                data.get("reason", ""),
            )
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("SignalToOrderRouter 发布 ORDER 事件失败: %s", exc)


def main(config: Dict[str, Any] | None = None):
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    strategy_id = cfg["strategy_id"]
    symbols = cfg["symbols"]
    days = int(cfg["days"])
    interval = float(cfg["tick_interval"])
    broker_mode = str(cfg.get("broker_mode", "sim"))
    market_source = str(cfg.get("market_source", "mock")).lower()
    enable_news_feed = bool(cfg.get("enable_news_feed", False))
    news_interval = float(cfg.get("news_poll_interval", 5.0))
    account_snapshot_interval = float(cfg.get("account_snapshot_interval", 10.0))

    logger.info("启动通用实时策略容器，策略ID=%s", strategy_id)

    # 1. EventBus
    bus = EventBus()
    # 显式启动，确保符合测试/生产一致行为
    if hasattr(bus, "start"):
        bus.start()

    # 2. 加载策略插件并创建实例
    manager = StrategyPluginManager()
    manager.scan_plugins()
    if strategy_id not in manager.plugins:
        raise SystemExit(f"策略插件 {strategy_id} 不存在，请检查 strategies/plugins 目录")

    plugin = manager.plugins[strategy_id]
    strategy = plugin.create_instance(params=None)

    # 某些策略需要显式注入 EventBus
    if hasattr(strategy, "initialize"):
        try:
            strategy.initialize(bus)
        except TypeError:
            # 对于只接受 (data, context) 的策略，忽略 initialize
            pass

    # 3. 创建订单执行器 / 券商适配层
    shared_broker: MyQuantBroker | None = None
    if broker_mode.lower() == "myquant":
        # 预先创建一个 MyQuantBroker 实例，供执行器与风控共享账户视图
        shared_broker = MyQuantBroker()
        SimpleOrderExecutor(bus, mode=broker_mode, broker=shared_broker)
    else:
        SimpleOrderExecutor(bus, mode=broker_mode)

    # 3.1 创建信号 -> 订单 路由器（将 SIGNAL/STRATEGY_SIGNAL 转为 ORDER）
    # 按当前设计，不再做“账户对齐券商资金/持仓”，统一使用固定初始资金风控，因此不传入 broker。
    router = SignalToOrderRouter(bus, base_quantity=100, broker=None)

    # 3.1.1 如使用 MyQuant 模式，则启动一个后台线程定期写入账户快照，供 UI 读取
    snapshot_scheduler: AccountSnapshotScheduler | None = None
    if shared_broker is not None:
        try:
            snapshot_scheduler = AccountSnapshotScheduler(shared_broker, interval=account_snapshot_interval)
            snapshot_scheduler.start()
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("创建 AccountSnapshotScheduler 失败: %s", exc)

    # 3.2 创建因子日志器（目前主要服务于 volume_price 插件）
    RealtimeFactorLogger(bus, strategy)

    # 3.3 创建实时风险监控器：基于 MARKET_DATA 更新风控持仓价格，并定期输出账户状态
    if router.risk_manager is not None:
        RealtimeRiskMonitor(bus, router.risk_manager, log_interval=60.0)

    # 3.4 可选：启动舆情/新闻流桥接，将财经快讯作为 EventType.NEWS 推送到 EventBus
    news_feed: RealtimeNewsFeed | None = None
    if enable_news_feed:
        try:
            news_feed = RealtimeNewsFeed(bus, symbols=symbols, interval=news_interval)
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("创建 RealtimeNewsFeed 失败: %s", exc)

    # 3.5 可选：发送一次测试信号，验证 SIGNAL->ORDER->BROKER->回报 链路
    if ENABLE_TEST_SIGNAL:
        try:
            test_symbol = str(TEST_SIGNAL_CONFIG.get("symbol", "000001.SZ"))
            direction = float(TEST_SIGNAL_CONFIG.get("direction", 1))
            strength = float(TEST_SIGNAL_CONFIG.get("strength", 1.0))
            price = float(TEST_SIGNAL_CONFIG.get("price", 10.0))
            reason = str(TEST_SIGNAL_CONFIG.get("reason", "test_manual_signal"))
            ts_now = datetime.now()

            test_evt = Event(
                type=EventType.SIGNAL,
                data={
                    "symbol": test_symbol,
                    "direction": direction,
                    "strength": strength,
                    "price": price,
                    "reason": reason,
                    "timestamp": ts_now,
                    "source": "TEST_SIGNAL",
                },
                timestamp=ts_now,
            )
            bus.publish(test_evt)
            logger.info(
                "[TEST] 已发布一次测试 SIGNAL: %s direction=%s price=%.2f strength=%.2f",
                test_symbol,
                direction,
                price,
                strength,
            )
        except Exception as exc:
            logger.warning("[TEST] 发送测试信号失败: %s", exc)

    # 4. 创建并启动实时行情源
    if market_source == "myquant":
        try:
            from astock_engine.market_myquant import MyQuantRealtimeDataFeed

            feed = MyQuantRealtimeDataFeed(bus, symbols=symbols, interval=interval)
            logger.info("使用 MyQuant 实时行情作为数据源")
        except Exception as exc:
            logger.warning("创建 MyQuantRealtimeDataFeed 失败，回退到 Mock 行情: %s", exc)
            feed = MockRealtimeDataFeed(bus, symbols=symbols, days=days, interval=interval)
    else:
        feed = MockRealtimeDataFeed(bus, symbols=symbols, days=days, interval=interval)

    start_ts = time.time()
    try:
        feed.run()
    except KeyboardInterrupt:
        logger.info("用户中断")

    elapsed = time.time() - start_ts
    logger.info("实时容器运行结束，用时 %.2f 秒", elapsed)

    # 5. 清理
    if hasattr(strategy, "shutdown"):
        try:
            strategy.shutdown()
        except Exception:
            pass
    if hasattr(bus, "stop"):
        bus.stop()
    # 6. 关闭新闻流
    try:
        if "news_feed" in locals() and news_feed is not None:
            news_feed.close()
    except Exception:
        pass

    # 7. 停止账户快照调度器
    try:
        if snapshot_scheduler is not None:
            snapshot_scheduler.stop()
    except Exception:
        pass


if __name__ == "__main__":
    main()

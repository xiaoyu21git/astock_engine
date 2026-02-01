"""SimulatedBroker 行为测试

验证基于 EventBus 的模拟券商是否能正确处理下单、更新资金/持仓，
以及通过 EventBus 推送撮合结果事件。
"""

import time

from astock_engine.core import EventBus, EventType, Event
from astock_engine.broker import SimulatedBroker
from astock_engine.broker.base import OrderRequest, OrderSide


def test_simulated_broker_direct_place_order_buy_sell():
    """直接调用 place_order，验证资金和持仓变动。"""
    bus = EventBus()
    bus.start()
    broker = SimulatedBroker(bus, initial_cash=100_000.0)

    # 订阅撮合结果事件
    order_responses = []
    trades = []

    def on_order_response(evt: Event):
        order_responses.append(evt)

    def on_trade(evt: Event):
        trades.append(evt)

    bus.subscribe(EventType.ORDER_RESPONSE, on_order_response)
    bus.subscribe(EventType.TRADE, on_trade)

    # 1) 买入 100 股，价格 10 元
    req_buy = OrderRequest(
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        price=10.0,
    )
    status_buy = broker.place_order(req_buy)

    time.sleep(0.1)  # 等待 EventBus 分发事件

    account = broker.query_account()
    positions = broker.query_positions()

    assert status_buy.status == "FILLED"
    assert len(order_responses) == 1
    assert len(trades) == 1

    # 现金应减少 100 * 10
    assert account["cash"] == 100_000.0 - 100 * 10.0
    # 持仓应为 100 股，均价 10 元
    assert positions["000001.SZ"]["quantity"] == 100
    assert positions["000001.SZ"]["avg_price"] == 10.0

    # 2) 卖出 40 股，价格 11 元
    req_sell = OrderRequest(
        symbol="000001.SZ",
        side=OrderSide.SELL,
        quantity=40,
        price=11.0,
    )
    status_sell = broker.place_order(req_sell)

    time.sleep(0.1)

    account2 = broker.query_account()
    positions2 = broker.query_positions()

    assert status_sell.status == "FILLED"
    # 现金应在原基础上增加 40 * 11
    assert account2["cash"] == account["cash"] + 40 * 11.0
    # 持仓数量应减少到 60 股
    assert positions2["000001.SZ"]["quantity"] == 60


def test_simulated_broker_handle_order_event_via_eventbus():
    """通过 EventBus 发布 ORDER 事件，验证自动触发下单。"""
    bus = EventBus()
    bus.start()
    broker = SimulatedBroker(bus, initial_cash=50_000.0)

    trades = []

    def on_trade(evt: Event):
        trades.append(evt)

    bus.subscribe(EventType.TRADE, on_trade)

    # 通过 EventBus 发布一个 ORDER 事件
    evt = Event(
        type=EventType.ORDER,
        data={
            "symbol": "600000.SH",
            "side": "BUY",
            "quantity": 50,
            "price": 12.3,
        },
    )
    bus.publish(evt)

    time.sleep(0.1)

    positions = broker.query_positions()
    account = broker.query_account()

    # 应该产生一笔成交
    assert len(trades) >= 1
    assert positions["600000.SH"]["quantity"] == 50
    # 现金应减少 50 * 12.3
    assert account["cash"] == 50_000.0 - 50 * 12.3

import asyncio
import pytest
from astock_engine.broker.myquant_broker import MyQuantBroker, OrderRequest, OrderSide, OrderType

@pytest.mark.asyncio
async def test_async_place_order_and_callback():
    broker = MyQuantBroker()
    # 下单前资金快照
    pre_snapshot = await broker.get_account_snapshot_async()
    pre_cash = pre_snapshot.get("cash")

    # 构造一个模拟下单请求（请根据实际环境调整 symbol/price/quantity）
    req = OrderRequest(
        symbol="000001.SZ",
        side=OrderSide.BUY,
        quantity=100,
        price=10.0,
        order_type=OrderType.LIMIT,
        client_order_id="test_async_001"
    )
    callback_result = {}
    def order_callback(order_status):
        callback_result["order_id"] = order_status.order_id
        callback_result["status"] = order_status.status
        callback_result["filled_quantity"] = order_status.filled_quantity
        callback_result["avg_price"] = order_status.avg_price

    # 异步下单并回调
    order_status = await broker.place_order_async(req, callback=order_callback)
    # 检查返回值和回调都能拿到结果
    assert order_status.order_id is not None
    assert order_status.status in ("NEW", "FILLED", "PARTIALLY_FILLED")
    assert callback_result["order_id"] == order_status.order_id
    print("异步下单回调结果：", callback_result)

    # 回调/成交后多次尝试获取资金快照，最多重试5次，每次间隔2秒
    max_retries = 5
    found_change = False
    for i in range(max_retries):
        await asyncio.sleep(2)
        post_snapshot = await broker.get_account_snapshot_async()
        post_cash = post_snapshot.get("cash")
        print(f"[第{i+1}次] 下单前资金: {pre_cash}, 下单后资金: {post_cash}")
        if (
            isinstance(pre_cash, (int, float))
            and isinstance(post_cash, (int, float))
            and pre_cash > 0 and post_cash > 0
            and post_cash != pre_cash
        ):
            found_change = True
            assert post_cash <= pre_cash, f"资金未减少: pre={pre_cash}, post={post_cash}"
            print("资金变化已捕获，测试通过")
            break
    if not found_change:
        print("资金快照不可用或未发生变化，跳过资金变化断言")

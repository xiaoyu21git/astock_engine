import pytest
import jqdatasdk
import time

# 请替换为你的聚宽账号和密码
def setup_module(module):
    jqdatasdk.auth('your_account', 'your_password')

@pytest.mark.order(1)
def test_jq_query_account():
    info = jqdatasdk.get_account_info()
    print('资金信息:', info)
    assert 'available_cash' in info

@pytest.mark.order(2)
def test_jq_place_order_and_check():
    # 下单前资金
    info_before = jqdatasdk.get_account_info()
    cash_before = info_before.get('available_cash', 0)
    print('下单前资金:', cash_before)

    # 下单（模拟盘/回测环境）
    order_id = jqdatasdk.order('000001.XSHE', 100)
    print('下单返回ID:', order_id)
    assert order_id is not None

    # 等待撮合
    time.sleep(3)

    # 下单后资金
    info_after = jqdatasdk.get_account_info()
    cash_after = info_after.get('available_cash', 0)
    print('下单后资金:', cash_after)
    assert cash_after <= cash_before

    # 查询持仓
    positions = jqdatasdk.get_positions()
    print('持仓:', positions)
    assert any(pos['security'] == '000001.XSHE' for pos in positions)

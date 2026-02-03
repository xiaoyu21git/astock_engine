import jqdatasdk
import pandas as pd
from datetime import datetime, timedelta
import json

# 本地配置缓存（简单实现，支持多级路径）
config_cache = {}

def set_config_cache(path, value):
    keys = path.split('.')
    d = config_cache
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value

def get_config(path, default=None):
    keys = path.split('.')
    d = config_cache
    for k in keys:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return default
    return d

def del_config_cache(path):
    keys = path.split('.')
    d = config_cache
    for k in keys[:-1]:
        d = d.get(k, {})
    d.pop(keys[-1], None)

try:
    import _native as eventbus_native
except ImportError:
    eventbus_native = None

JQ_USER = "13552314165"
JQ_PASS = "xiaoyu21A"

def jq_auth():
    jqdatasdk.auth(JQ_USER, JQ_PASS)
    info = jqdatasdk.get_query_count()
    print(f"[聚宽] 登录成功，剩余可用条数: {info}")

def test_all():
    jq_auth()
    # 1. 查询全A股列表
    print("\n[1] 全A股列表（前5行）:")
    stocks = jqdatasdk.get_all_securities(['stock'])
    print(stocks.head())

    # 2. 查询日线行情
    print("\n[2] 日线行情:")
    df = jqdatasdk.get_price('000001.XSHE', count=5, end_date='2024-01-01', frequency='daily')
    print(df)

    # 3. 查询分钟线行情
    print("\n[3] 分钟线行情:")
    df_min = jqdatasdk.get_price('000001.XSHE', count=5, end_date='2024-01-01 14:55:00', frequency='1m')
    print(df_min)

    # 4. 查询财务数据
    print("\n[4] 财务数据:")
    q = jqdatasdk.query(jqdatasdk.income.statDate, jqdatasdk.income.net_profit).filter(jqdatasdk.income.code=='000001.XSHE')
    df_fin = jqdatasdk.get_fundamentals(q, statDate='2023')
    print(df_fin)

    # 5. 查询指数列表
    print("\n[5] 指数列表:")
    idx = jqdatasdk.get_all_securities(['index'])
    print(idx.head())

    # 6. 查询基金列表
    print("\n[6] 基金列表:")
    funds = jqdatasdk.get_all_securities(['fund'])
    print(funds.head())

    # 7. 查询期货列表
    print("\n[7] 期货列表:")
    futs = jqdatasdk.get_all_securities(['futures'])
    print(futs.head())

    # 8. 宏观经济数据
    print("\n[8] 宏观经济数据:")
    try:
        macro = jqdatasdk.get_macro('GDP_quarter')
        print(macro.head())
    except Exception as e:
        print("宏观数据需付费/权限:", e)

    # 9. 公告
    print("\n[9] 公告:")
    try:
        ann = jqdatasdk.get_query_conditions('notice')
        print(ann)
    except Exception as e:
        print("公告接口需权限:", e)

    # 10. 限售解禁
    print("\n[10] 限售解禁:")
    try:
        xs = jqdatasdk.get_locked_shares('000001.XSHE', '2023-01-01', '2024-01-01')
        print(xs)
    except Exception as e:
        print("限售接口需权限:", e)

    # 11. 分红
    print("\n[11] 分红:")
    try:
        bonus = jqdatasdk.get_dividends('000001.XSHE')
        print(bonus.head())
    except Exception as e:
        print("分红接口需权限:", e)

    # 12. 概念板块
    print("\n[12] 概念板块:")
    try:
        concept = jqdatasdk.get_concept()
        print(concept.head())
    except Exception as e:
        print("概念接口需权限:", e)

    # 13. 行业分类
    print("\n[13] 行业分类:")
    try:
        industry = jqdatasdk.get_industry()
        print(industry.head())
    except Exception as e:
        print("行业接口需权限:", e)

    # 14. 龙虎榜
    print("\n[14] 龙虎榜:")
    try:
        lhb = jqdatasdk.get_billboard_list(stock_list=['000001.XSHE'], start_date='2023-01-01', end_date='2024-01-01')
        print(lhb.head())
    except Exception as e:
        print("龙虎榜接口需权限:", e)

    # 15. 停复牌
    print("\n[15] 停复牌:")
    try:
        susp = jqdatasdk.get_extras('is_paused', ['000001.XSHE'], start_date='2024-01-01', end_date='2024-01-10')
        print(susp)
    except Exception as e:
        print("停复牌接口需权限:", e)

    # 16. 资金流向（聚宽免费不支持，接口占位）
    print("\n[16] 资金流向:（聚宽免费无此接口，仅占位）")

    # 订阅配置变更事件
    if eventbus_native is not None:
        bus = eventbus_native.get_engine_bus()
        def on_config_changed(evt):
            data_json = evt.get_string("data")
            if data_json:
                data = json.loads(data_json)
                print("[CONFIG_CHANGED] domain:", data.get("domain"),
                      "path:", data.get("path"),
                      "old_value:", data.get("old_value"),
                      "new_value:", data.get("new_value"),
                      "timestamp:", data.get("timestamp"))
                # TODO: 在此处更新本地配置缓存或触发业务逻辑
            else:
                print("[CONFIG_CHANGED] event received, but no data field.")
        bus.subscribe("CONFIG_CHANGED", on_config_changed)
    else:
        print("[WARN] eventbus_native not available, cannot subscribe to CONFIG_CHANGED events.")

    # 订阅配置相关事件
    if eventbus_native is not None:
        bus = eventbus_native.get_engine_bus()
        def on_config_event(evt):
            data_json = evt.get_string("data")
            if data_json:
                data = json.loads(data_json)
                event_type = data.get("type")
                if event_type == "CONFIG_CHANGED":
                    # 单项变更
                    path = data.get("path")
                    new_value = data.get("new_value")
                    set_config_cache(path, new_value)
                elif event_type == "CONFIG_BATCH_CHANGED":
                    for c in data.get("changes", []):
                        set_config_cache(c.get("path"), c.get("new_value"))
                elif event_type == "CONFIG_UNDO":
                    for c in data.get("changes", []):
                        set_config_cache(c.get("path"), c.get("to_value"))
                elif event_type == "CONFIG_ROLLBACK":
                    for c in data.get("changes", []):
                        set_config_cache(c.get("path"), c.get("to_value"))
                else:
                    print(f"[UNKNOWN CONFIG EVENT] {event_type}", data)
            else:
                print("[CONFIG EVENT] event received, but no data field.")
        bus.subscribe("CONFIG_CHANGED", on_config_event)
        bus.subscribe("CONFIG_BATCH_CHANGED", on_config_event)
        bus.subscribe("CONFIG_UNDO", on_config_event)
        bus.subscribe("CONFIG_ROLLBACK", on_config_event)
    else:
        print("[WARN] eventbus_native not available, cannot subscribe to config events.")

if __name__ == '__main__':
    test_all()

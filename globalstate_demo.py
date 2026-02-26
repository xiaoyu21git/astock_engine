# globalstate_demo.py
from _native import GlobalState
import os
import json

gs = GlobalState()

def on_match_changed(val):
    print(f"撮合方式变更: {val}")

def on_token_changed(val):
    print(f"Token变更: {val}")

def on_accountid_changed(val):
    print(f"账户ID变更: {val}")

gs.onUsePreciseMatchChanged(on_match_changed)
gs.onTokenChanged(on_token_changed)
gs.onAccountIdChanged(on_accountid_changed)

# 主动修改属性，触发 C++/QML/Python 联动
print("当前撮合方式:", gs.usePreciseMatch)
gs.usePreciseMatch = True
gs.token = "mytoken123"
gs.accountId = "account_001"

# 自动从配置文件读取掘金账号密码
config_path = os.path.join(os.path.dirname(__file__), '../config/data_source.json')
JQ_USERNAME = None
JQ_PASSWORD = None
if os.path.exists(config_path):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            JQ_USERNAME = cfg.get('jq_username')
            JQ_PASSWORD = cfg.get('jq_password')
    except Exception as e:
        print("读取配置文件失败:", e)

# 支持自动读取 bin/config/config.json 中 juejin.token/account_id
config_path2 = os.path.join(os.path.dirname(__file__), '../bin/config/config.json')
if os.path.exists(config_path2):
    try:
        with open(config_path2, 'r', encoding='utf-8') as f:
            cfg2 = json.load(f)
            juejin = cfg2.get('juejin', {})
            if juejin.get('token'):
                gs.token = juejin['token']
                print("已自动设置掘金token:", gs.token)
            if juejin.get('account_id'):
                gs.accountId = juejin['account_id']
                print("已自动设置掘金account_id:", gs.accountId)
    except Exception as e:
        print("读取 juejin 配置失败:", e)

# 掘金连接测试
try:
    import jqdatasdk
    if JQ_USERNAME and JQ_PASSWORD:
        jqdatasdk.auth(JQ_USERNAME, JQ_PASSWORD)
        is_connected = jqdatasdk.is_auth()
        print("掘金连接状态:", "已连接" if is_connected else "未连接")
    else:
        print("配置文件未包含 jq_username 或 jq_password")
except ImportError:
    print("未安装 jqdatasdk，无法测试掘金连接。请 pip install jqdatasdk")
except Exception as e:
    print("掘金连接异常:", e)

# 掘金模拟盘API测试（仅用token/account_id）
def test_juejin_sim_account():
    try:
        import requests
        import json
        session = requests.Session()
        # 读取掘金账号密码
        config_path2 = os.path.join(os.path.dirname(__file__), '../bin/config/config.json')
        jq_user = None
        jq_pwd = None
        if os.path.exists(config_path2):
            with open(config_path2, 'r', encoding='utf-8') as f:
                cfg2 = json.load(f)
                jq_user = cfg2.get('jq_username') or (cfg2.get('joinquant') or {}).get('user')
                jq_pwd = cfg2.get('jq_password') or (cfg2.get('joinquant') or {}).get('password')
        if gs.token and gs.accountId:
            url = "https://www.myquant.cn/api/v1/portfolio/{}/assets".format(gs.accountId)
            headers = {"Authorization": "Bearer {}".format(gs.token)}
            resp = session.get(url, headers=headers, timeout=10)
            content_type = resp.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                try:
                    data = resp.json()
                    print("模拟盘资产信息:", data)
                    return
                except Exception as e:
                    print("API返回内容无法解析为JSON，原始内容：\n{}".format(resp.text))
            elif 'text/html' in content_type and jq_user and jq_pwd:
                print("API返回HTML，尝试模拟登录...\n")
                # 掘金登录表单接口（如有变动请抓包修正）
                login_url = "https://www.myquant.cn/auth/login"
                login_data = {"username": jq_user, "password": jq_pwd}
                login_headers = {"Content-Type": "application/json"}
                login_resp = session.post(login_url, data=json.dumps(login_data), headers=login_headers, timeout=10)
                if login_resp.status_code == 200 and 'application/json' in login_resp.headers.get('Content-Type', ''):
                    print("登录成功，重新请求资产API...")
                    resp2 = session.get(url, headers=headers, timeout=10)
                    if 'application/json' in resp2.headers.get('Content-Type', ''):
                        print("模拟盘资产信息:", resp2.json())
                    else:
                        print("登录后API返回内容：\n{}".format(resp2.text[:500]))
                else:
                    print("登录失败，返回内容：\n{}".format(login_resp.text[:500]))
            else:
                print("API返回未知类型({})，内容：\n{}".format(content_type, resp.text[:500]))
        else:
            print("未检测到有效的掘金token或account_id，无法测试模拟盘API")
    except ImportError:
        print("未安装 requests 库，无法测试掘金模拟盘API。请 pip install requests")
    except Exception as e:
        print("掘金模拟盘API请求异常:", e)

# 测试 easytrader 自动化登录国投安信证券客户端并查询资金、持仓
def test_gtja_jq3():
    try:
        import easytrader
        import time
        import os
        import sys
        # 支持通过环境变量或脚本顶部变量自定义券商客户端路径
        # 优先级：环境变量 > 脚本变量 > 默认自动查找
        GTJA_JQ3_PATH = os.environ.get('GTJA_JQ3_PATH', None)
        # 如需硬编码路径可在此处修改
        DEFAULT_GTJA_JQ3_PATH = r'D:/Program Files (x86)/Essence Goldminer3/xiadan.exe'
        if not GTJA_JQ3_PATH:
            GTJA_JQ3_PATH = DEFAULT_GTJA_JQ3_PATH
        if not os.path.exists(GTJA_JQ3_PATH):
            print(f"券商客户端路径不存在: {GTJA_JQ3_PATH}\n请检查路径是否正确，或设置环境变量GTJA_JQ3_PATH为实际安装路径。")
            sys.exit(1)
        user = easytrader.use('gj_client')
        user.prepare(GTJA_JQ3_PATH)
        print('登录成功')
        balance = user.balance
        print('资金信息:', balance)
        position = user.position
        print('持仓信息:', position)
        # 测试下单（请用小金额或模拟环境，避免真实资金风险）
        # 示例：买入 600000.SH 100股 市价单
        try:
            order_result = user.buy('600000', 100, price=0, entrust_bs='买入')
            print('下单结果:', order_result)
        except Exception as oe:
            print('下单异常:', oe)
        time.sleep(2)
        # 测试撤单（撤销所有当日未成交订单）
        try:
            entrusts = user.entrust
            print('当日委托:', entrusts)
            for entrust in entrusts:
                if entrust.get('状态', '').find('未成交') != -1:
                    cancel_result = user.cancel_entrust(entrust['委托编号'])
                    print('撤单结果:', cancel_result)
        except Exception as ce:
            print('撤单异常:', ce)
    except Exception as e:
        print('easytrader 国投掘金3 测试异常:', e)

if __name__ == "__main__":
    test_gtja_jq3()

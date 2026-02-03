# globalstate_demo.py
from globalstate_native import GlobalState

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

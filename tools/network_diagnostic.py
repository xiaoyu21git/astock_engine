"""
网络配置检查和修复工具
"""
import os
import sys

print("=" * 70)
print("       网络诊断工具")
print("=" * 70)
print()

# 1. 检查代理设置
print("【1. 当前代理设置】")
http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')

if http_proxy:
    print(f"   HTTP_PROXY: {http_proxy}")
else:
    print("   HTTP_PROXY: 未设置")

if https_proxy:
    print(f"   HTTPS_PROXY: {https_proxy}")
else:
    print("   HTTPS_PROXY: 未设置")

print()

# 2. 测试连接
print("【2. 测试数据源连接】")
import requests

test_urls = {
    '东方财富': 'https://push2his.eastmoney.com',
    '新浪财经': 'https://hq.sinajs.cn',
    'AkShare备用': 'https://stock.finance.sina.com.cn'
}

for name, url in test_urls.items():
    try:
        # 不使用代理测试
        session = requests.Session()
        session.trust_env = False  # 忽略系统代理
        response = session.get(url, timeout=5)
        print(f"   ✅ {name}: 连接正常 (状态码 {response.status_code})")
    except Exception as e:
        print(f"   ❌ {name}: 连接失败 - {type(e).__name__}")

print()

# 3. 给出建议
print("=" * 70)
print("💡 解决方案")
print("=" * 70)
print()

if http_proxy or https_proxy:
    print("【问题】检测到代理设置，但代理服务器无法连接")
    print()
    print("🔧 方案1：临时禁用代理（推荐）")
    print("   在PowerShell中运行：")
    print("   ")
    print("   $env:HTTP_PROXY=''")
    print("   $env:HTTPS_PROXY=''")
    print("   .venv\\Scripts\\python.exe astock_engine\\examples\\test_volume_price_strategy.py")
    print()
    print("🔧 方案2：永久禁用系统代理")
    print("   打开 Windows设置 → 网络和Internet → 代理")
    print("   关闭 \"使用代理服务器\"")
    print()
else:
    print("【问题】未检测到代理设置，但仍然连接失败")
    print()
    print("🔧 方案1：检查防火墙")
    print("   允许Python访问网络")
    print()
    print("🔧 方案2：更换网络环境")
    print("   切换到稳定的网络（如手机热点）")
    print()

print("🔧 方案3：使用离线数据（最可靠）")
print("   我可以帮您创建一个模拟数据生成器")
print("   用真实的历史数据特征生成测试数据")
print()
print("🔧 方案4：更换数据源")
print("   - 使用Tushare（需要注册token）")
print("   - 使用yfinance（需要科学上网）")
print()

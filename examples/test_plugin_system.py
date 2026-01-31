"""
测试策略插件系统
"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from astock_engine.strategies.plugin_manager import StrategyPluginManager, get_plugin_manager
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def main():
    print("\n" + "="*80)
    print("策略插件系统测试")
    print("="*80 + "\n")
    
    # 1. 创建插件管理器
    logger.info("1️⃣  创建插件管理器...")
    manager = get_plugin_manager()
    
    # 2. 扫描插件
    logger.info("\n2️⃣  扫描插件目录...")
    count = manager.scan_plugins()
    print(f"\n✅ 发现 {count} 个策略插件\n")
    
    # 3. 列出所有插件
    logger.info("3️⃣  列出所有插件...")
    plugins = manager.list_plugins()
    
    print("\n" + "="*80)
    print("已加载的策略插件")
    print("="*80)
    
    for i, plugin_info in enumerate(plugins, 1):
        meta = plugin_info['metadata']
        print(f"\n【插件 {i}】")
        print(f"  ID:       {plugin_info['plugin_id']}")
        print(f"  名称:     {meta['name']}")
        print(f"  版本:     {meta['version']}")
        print(f"  作者:     {meta['author']}")
        print(f"  类别:     {meta['category']}")
        print(f"  描述:     {meta['description']}")
        print(f"  标签:     {', '.join(meta['tags'])}")
        print(f"  类名:     {plugin_info['class_name']}")
        print(f"  实例数:   {plugin_info['active_instances']}")
        
        # 参数信息
        if meta.get('parameters'):
            print(f"  参数:")
            for param_name, param_info in meta['parameters'].items():
                print(f"    - {param_name}: {param_info.get('description', '')}")
                print(f"      类型={param_info['type']}, 默认={param_info['default']}")
    
    # 4. 获取策略类别
    logger.info("\n4️⃣  策略类别统计...")
    categories = manager.get_categories()
    print(f"\n策略类别: {', '.join(categories)}")
    
    # 5. 搜索测试
    logger.info("\n5️⃣  搜索插件...")
    keyword = "均线"
    search_results = manager.search_plugins(keyword)
    print(f"\n搜索 '{keyword}' 的结果: {len(search_results)} 个")
    for result in search_results:
        print(f"  - {result['metadata']['name']}")
    
    # 6. 创建策略实例
    logger.info("\n6️⃣  创建策略实例...")
    if plugins:
        plugin_id = plugins[0]['plugin_id']
        
        try:
            strategy_params = {
                'short_window': 5,
                'long_window': 20,
                'initial_capital': 1000000
            }
            
            strategy = manager.create_strategy(plugin_id, params=strategy_params)
            
            print(f"\n✅ 成功创建策略实例:")
            print(f"  策略名称: {strategy.name}")
            print(f"  初始资金: ¥{strategy.initial_capital:,.0f}")
            print(f"  参数: {strategy_params}")
            
        except Exception as e:
            logger.error(f"创建策略实例失败: {e}", exc_info=True)
    
    # 7. 导出插件列表
    logger.info("\n7️⃣  导出插件列表...")
    output_file = "plugins_list.json"
    manager.export_plugin_list(output_file)
    print(f"\n插件列表已导出到: {output_file}")
    
    print("\n" + "="*80)
    print("测试完成")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()

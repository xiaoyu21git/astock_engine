"""
策略插件管理器
支持动态加载、热插拔、插件市场
"""
import os
import sys
import json
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, List, Type, Optional, Any
from datetime import datetime
import logging

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class StrategyMetadata:
    """策略元数据"""
    
    def __init__(self, data: Dict):
        self.name = data.get('name', 'Unknown')
        self.version = data.get('version', '1.0.0')
        self.author = data.get('author', 'Anonymous')
        self.description = data.get('description', '')
        self.category = data.get('category', 'other')
        self.tags = data.get('tags', [])
        self.parameters = data.get('parameters', {})
        self.dependencies = data.get('dependencies', [])
        self.enabled = data.get('enabled', True)
        self.created_at = data.get('created_at', datetime.now().isoformat())
        self.updated_at = data.get('updated_at', datetime.now().isoformat())
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'version': self.version,
            'author': self.author,
            'description': self.description,
            'category': self.category,
            'tags': self.tags,
            'parameters': self.parameters,
            'dependencies': self.dependencies,
            'enabled': self.enabled,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class StrategyPlugin:
    """策略插件封装"""
    
    def __init__(self, 
                 plugin_id: str,
                 strategy_class: Type[BaseStrategy],
                 metadata: StrategyMetadata,
                 plugin_path: str):
        self.plugin_id = plugin_id
        self.strategy_class = strategy_class
        self.metadata = metadata
        self.plugin_path = plugin_path
        self.instances: List[BaseStrategy] = []
    
    def create_instance(self, params: Dict = None) -> BaseStrategy:
        """创建策略实例"""
        instance = self.strategy_class(params=params)
        self.instances.append(instance)
        logger.info(f"创建策略实例: {self.metadata.name} ({self.plugin_id})")
        return instance
    
    def get_info(self) -> Dict:
        """获取插件信息"""
        return {
            'plugin_id': self.plugin_id,
            'class_name': self.strategy_class.__name__,
            'metadata': self.metadata.to_dict(),
            'plugin_path': self.plugin_path,
            'active_instances': len(self.instances)
        }


class StrategyPluginManager:
    """策略插件管理器"""
    
    def __init__(self, plugin_dirs: List[str] = None):
        """
        初始化插件管理器
        
        Args:
            plugin_dirs: 插件目录列表
        """
        self.plugins: Dict[str, StrategyPlugin] = {}
        self.plugin_dirs = plugin_dirs or []
        
        # 添加默认插件目录
        default_dir = Path(__file__).parent / 'plugins'
        if str(default_dir) not in self.plugin_dirs:
            self.plugin_dirs.append(str(default_dir))
        
        # 确保插件目录存在
        for dir_path in self.plugin_dirs:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"策略插件管理器初始化，插件目录: {self.plugin_dirs}")
    
    def scan_plugins(self) -> int:
        """
        扫描并加载所有插件
        
        Returns:
            加载的插件数量
        """
        loaded_count = 0
        
        for plugin_dir in self.plugin_dirs:
            plugin_path = Path(plugin_dir)
            
            if not plugin_path.exists():
                logger.warning(f"插件目录不存在: {plugin_dir}")
                continue
            
            # 扫描所有策略插件
            for item in plugin_path.iterdir():
                if item.is_dir() and not item.name.startswith('_'):
                    # 检查是否有 strategy.py 和 metadata.json
                    strategy_file = item / 'strategy.py'
                    metadata_file = item / 'metadata.json'
                    
                    if strategy_file.exists():
                        try:
                            plugin_id = item.name
                            self.load_plugin(plugin_id, str(item))
                            loaded_count += 1
                        except Exception as e:
                            logger.error(f"加载插件失败 {item.name}: {e}", exc_info=True)
        
        logger.info(f"扫描完成，共加载 {loaded_count} 个插件")
        return loaded_count
    
    def load_plugin(self, plugin_id: str, plugin_path: str) -> StrategyPlugin:
        """
        加载单个插件
        
        Args:
            plugin_id: 插件ID
            plugin_path: 插件路径
            
        Returns:
            StrategyPlugin对象
        """
        plugin_path_obj = Path(plugin_path)
        
        # 1. 加载元数据
        metadata_file = plugin_path_obj / 'metadata.json'
        if metadata_file.exists():
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata_data = json.load(f)
        else:
            # 使用默认元数据
            metadata_data = {
                'name': plugin_id,
                'version': '1.0.0',
                'description': f'Strategy plugin: {plugin_id}'
            }
        
        metadata = StrategyMetadata(metadata_data)
        
        # 检查是否启用
        if not metadata.enabled:
            logger.info(f"插件 {plugin_id} 已禁用，跳过加载")
            return None
        
        # 2. 动态加载策略类
        strategy_file = plugin_path_obj / 'strategy.py'
        
        # 使用importlib动态导入
        spec = importlib.util.spec_from_file_location(
            f"strategy_plugin_{plugin_id}",
            strategy_file
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 查找策略类（必须继承BaseStrategy）
        strategy_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, BaseStrategy) and 
                attr != BaseStrategy):
                strategy_class = attr
                break
        
        if not strategy_class:
            raise ValueError(f"插件 {plugin_id} 中未找到有效的策略类")
        
        # 3. 创建插件对象
        plugin = StrategyPlugin(
            plugin_id=plugin_id,
            strategy_class=strategy_class,
            metadata=metadata,
            plugin_path=str(plugin_path_obj)
        )
        
        # 4. 注册插件
        self.plugins[plugin_id] = plugin
        
        logger.info(f"✅ 加载插件: {metadata.name} v{metadata.version} ({plugin_id})")
        return plugin
    
    def unload_plugin(self, plugin_id: str) -> bool:
        """
        卸载插件
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            是否成功卸载
        """
        if plugin_id not in self.plugins:
            logger.warning(f"插件 {plugin_id} 不存在")
            return False
        
        plugin = self.plugins[plugin_id]
        
        # 停止所有实例
        for instance in plugin.instances:
            if hasattr(instance, 'shutdown'):
                instance.shutdown()
        
        # 移除插件
        del self.plugins[plugin_id]
        
        logger.info(f"卸载插件: {plugin_id}")
        return True
    
    def reload_plugin(self, plugin_id: str) -> bool:
        """
        重新加载插件（热更新）
        
        Args:
            plugin_id: 插件ID
            
        Returns:
            是否成功重载
        """
        if plugin_id not in self.plugins:
            logger.warning(f"插件 {plugin_id} 不存在")
            return False
        
        plugin_path = self.plugins[plugin_id].plugin_path
        
        # 卸载并重新加载
        self.unload_plugin(plugin_id)
        
        try:
            self.load_plugin(plugin_id, plugin_path)
            logger.info(f"🔄 插件重载成功: {plugin_id}")
            return True
        except Exception as e:
            logger.error(f"插件重载失败: {e}", exc_info=True)
            return False
    
    def get_plugin(self, plugin_id: str) -> Optional[StrategyPlugin]:
        """获取插件"""
        return self.plugins.get(plugin_id)
    
    def create_strategy(self, plugin_id: str, params: Dict = None) -> BaseStrategy:
        """
        创建策略实例
        
        Args:
            plugin_id: 插件ID
            params: 策略参数
            
        Returns:
            策略实例
        """
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            raise ValueError(f"插件 {plugin_id} 不存在")
        
        return plugin.create_instance(params)
    
    def list_plugins(self, category: str = None, enabled_only: bool = True) -> List[Dict]:
        """
        列出所有插件
        
        Args:
            category: 过滤类别
            enabled_only: 只列出启用的插件
            
        Returns:
            插件信息列表
        """
        result = []
        
        for plugin in self.plugins.values():
            # 过滤条件
            if enabled_only and not plugin.metadata.enabled:
                continue
            
            if category and plugin.metadata.category != category:
                continue
            
            result.append(plugin.get_info())
        
        return result
    
    def get_categories(self) -> List[str]:
        """获取所有策略类别"""
        categories = set()
        for plugin in self.plugins.values():
            categories.add(plugin.metadata.category)
        return sorted(list(categories))
    
    def search_plugins(self, keyword: str) -> List[Dict]:
        """
        搜索插件
        
        Args:
            keyword: 关键词
            
        Returns:
            匹配的插件列表
        """
        result = []
        keyword_lower = keyword.lower()
        
        for plugin in self.plugins.values():
            # 搜索名称、描述、标签
            if (keyword_lower in plugin.metadata.name.lower() or
                keyword_lower in plugin.metadata.description.lower() or
                any(keyword_lower in tag.lower() for tag in plugin.metadata.tags)):
                result.append(plugin.get_info())
        
        return result
    
    def export_plugin_list(self, output_file: str):
        """导出插件列表到JSON文件"""
        plugins_data = [plugin.get_info() for plugin in self.plugins.values()]
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(plugins_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"插件列表已导出到: {output_file}")


# 全局插件管理器单例
_global_manager: Optional[StrategyPluginManager] = None


def get_plugin_manager() -> StrategyPluginManager:
    """获取全局插件管理器"""
    global _global_manager
    if _global_manager is None:
        _global_manager = StrategyPluginManager()
    return _global_manager

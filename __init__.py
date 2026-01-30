# # astock_engine/__init__.py
# """
# ASTOCK Quant Engine - Python Interface
# Version: 0.0.1
# """

# import os
# import sys
# import importlib.util
# from pathlib import Path

# __version__ = "0.0.1"
# __author__ = "ASTOCK Team"

# # ==================== 全局变量定义 ====================
# _has_native = False  # 先定义，防止未定义错误
# _native_module = None

# # ==================== 动态加载C++扩展 ====================
# def _load_native_extension():
#     """加载C++原生扩展模块"""
#     global _has_native, _native_module
    
#     print("DEBUG: Attempting to load native extension...")
    
#     # 当前文件所在目录
#     current_dir = Path(__file__).parent
#     project_root = current_dir.parent
    
#     print(f"DEBUG: Current dir: {current_dir}")
#     print(f"DEBUG: Project root: {project_root}")
    
#     # 可能的扩展文件位置（优先级从高到低）
#     search_paths = [
#         # 1. 当前目录（直接构建输出）
#         current_dir,
#         # 2. 构建目录（CMake构建）
#         project_root / "build" / "lib",
#         project_root / "build",
#         # 3. 开发构建目录
#         project_root / "bin",
#         project_root / "bin_debug",
#         # 4. 用户site-packages
#         Path(sys.prefix) / "Lib" / "site-packages" / "astock_engine",
#         Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages" / "astock_engine",
#     ]
    
#     # 可能的扩展文件名（根据不同平台）
#     module_base_name = "_native"
    
#     # 平台特定的后缀
#     if sys.platform == "win32":
#         suffixes = [".pyd", ".dll", ""]
#     elif sys.platform == "darwin":
#         suffixes = [".so", ".dylib", ""]
#     else:  # linux
#         suffixes = [".so", ""]
    
#     # 添加Python版本特定的后缀
#     python_suffix = f".cpython-{sys.version_info.major}{sys.version_info.minor}"
#     if sys.platform == "win32":
#         python_suffix += f"-win_amd64"
#     elif sys.platform == "darwin":
#         python_suffix += f"-darwin"
    
#     # 构建完整的搜索列表
#     module_names = []
#     for suffix in suffixes:
#         # 基础名称
#         module_names.append(f"{module_base_name}{suffix}")
#         # Python扩展名称
#         module_names.append(f"{module_base_name}{python_suffix}{suffix}")
    
#     print(f"DEBUG: Searching for modules: {module_names}")
#     print(f"DEBUG: Search paths: {search_paths}")
    
#     # 搜索模块文件
#     module_path = None
#     for search_path in search_paths:
#         if not search_path.exists():
#             print(f"DEBUG: Path does not exist: {search_path}")
#             continue
            
#         for module_name in module_names:
#             test_path = search_path / module_name
#             print(f"DEBUG: Trying: {test_path}")
#             if test_path.exists():
#                 module_path = test_path
#                 print(f"DEBUG: Found module at: {module_path}")
#                 break
        
#         if module_path:
#             break
    
#     if not module_path:
#         print("WARNING: Native extension not found in any search path")
#         _has_native = False
#         return False
    
#     # 加载模块
#     try:
#         # 将模块所在目录添加到sys.path
#         module_dir = module_path.parent
#         if str(module_dir) not in sys.path:
#             sys.path.insert(0, str(module_dir))
#             print(f"DEBUG: Added to sys.path: {module_dir}")
        
#         # 使用importlib加载模块
#         spec = importlib.util.spec_from_file_location(
#             "astock_engine._native", 
#             module_path
#         )
#         if spec is None:
#             print(f"ERROR: Failed to create spec from {module_path}")
#             _has_native = False
#             return False
            
#         _native_module = importlib.util.module_from_spec(spec)
        
#         # 将模块安装到sys.modules
#         sys.modules["astock_engine._native"] = _native_module
        
#         # 执行模块
#         spec.loader.exec_module(_native_module)
        
#         print(f"DEBUG: Successfully loaded module: {_native_module}")
        
#         # 导出模块的所有公共属性
#         for attr_name in dir(_native_module):
#             if not attr_name.startswith("_"):
#                 attr_value = getattr(_native_module, attr_name)
#                 globals()[attr_name] = attr_value
#                 print(f"DEBUG: Exported {attr_name}")
        
#         _has_native = True
#         print("INFO: C++ native extension loaded successfully")
#         return True
        
#     except Exception as e:
#         print(f"ERROR: Failed to load native extension: {e}")
#         import traceback
#         traceback.print_exc()
#         _has_native = False
#         return False

# # ==================== 尝试加载原生扩展 ====================
# print("INFO: Initializing ASTOCK Quant Engine Python interface...")
# _load_native_extension()

# # ==================== Python回退实现 ====================
# if not _has_native:
#     print("WARNING: Using Python fallback implementation for core functionality")
    
#     # 必须定义在尝试导入时可能用到的类
#     class MarketData:
#         """市场数据类（Python回退）"""
#         def __init__(self):
#             self.symbol = ""
#             self.last_price = 0.0
#             self.volume = 0
#             self.timestamp = ""
        
#         def __repr__(self):
#             return f"MarketData(symbol={self.symbol}, price={self.last_price})"
    
#     class Order:
#         """订单类（Python回退）"""
#         def __init__(self):
#             self.order_id = ""
#             self.symbol = ""
#             self.side = "BUY"
#             self.price = 0.0
#             self.quantity = 0
        
#         def __repr__(self):
#             return f"Order(id={self.order_id}, {self.side} {self.symbol} x{self.quantity} @ {self.price})"
    
#     class Logger:
#         """日志类（Python回退）"""
#         @staticmethod
#         def info(message):
#             print(f"[INFO] {message}")
        
#         @staticmethod
#         def warning(message):
#             print(f"[WARNING] {message}")
        
#         @staticmethod
#         def error(message):
#             print(f"[ERROR] {message}")
    
#     class QuantEngine:
#         """量化引擎（Python回退）"""
#         def __init__(self, config=None):
#             self._running = False
#             self._config = config or {}
#             print(f"Python fallback QuantEngine initialized with config: {config}")
        
#         def initialize(self):
#             """初始化引擎"""
#             print("Python fallback engine initializing...")
#             return True
        
#         def start(self):
#             """启动引擎"""
#             self._running = True
#             print("Python fallback engine started")
#             return True
        
#         def stop(self):
#             """停止引擎"""
#             self._running = False
#             print("Python fallback engine stopped")
#             return True
        
#         def is_running(self):
#             """检查是否运行中"""
#             return self._running
        
#         def subscribe(self, symbol):
#             """订阅行情"""
#             print(f"Python fallback: Subscribed to {symbol}")
#             return True
        
#         def unsubscribe(self, symbol):
#             """取消订阅"""
#             print(f"Python fallback: Unsubscribed from {symbol}")
#             return True
        
#         def __repr__(self):
#             return f"QuantEngine(running={self._running})"

# # ==================== 确保_has_native已定义 ====================
# # 再次检查，确保变量已定义
# if '_has_native' not in globals():
#     _has_native = False
#     print("WARNING: _has_native was not properly defined, setting to False")

# # ==================== 导出公共API ====================
# # 确定要导出的内容
# __all__ = []

# # 导出核心类
# for cls_name in ['QuantEngine', 'MarketData', 'Order', 'Logger']:
#     if cls_name in globals():
#         __all__.append(cls_name)

# # 导出其他变量
# __all__.extend(['__version__', '__author__', '_has_native'])

# # 打印初始化完成信息
# print(f"INFO: ASTOCK Quant Engine v{__version__} initialized")
# print(f"INFO: Native extension loaded: {_has_native}")

# # ==================== 测试函数 ====================
# def test_import():
#     """测试导入是否成功"""
#     print("=" * 50)
#     print("ASTOCK Quant Engine Import Test")
#     print("=" * 50)
#     print(f"Version: {__version__}")
#     print(f"Native extension: {'LOADED' if _has_native else 'NOT LOADED (using fallback)'}")
#     print(f"Available classes: {[c for c in ['QuantEngine', 'MarketData'] if c in globals()]}")
    
#     # 测试创建对象
#     try:
#         engine = QuantEngine()
#         print(f"QuantEngine created: {engine}")
#         return True
#     except Exception as e:
#         print(f"Error creating engine: {e}")
#         return False

# # 如果直接运行此文件，执行测试
# if __name__ == "__main__":
#     test_import()

# astock_engine/__init__.py
# astock_engine/__init__.py
"""
ASTOCK Quant Engine - Python Interface
"""

__version__ = "0.1.0"
__author__ = "ASTOCK Team"

# 导入core模块
from .core import EventBus, EventType, Event, create_event

# 导出公共API
__all__ = [
    "__version__",
    "__author__",
    "EventBus",
    "EventType", 
    "Event",
    "create_event",
    # 兼容层: 提供 EventFormat / EventValue 给测试套件和现有代码使用
    "EventFormat",
    "EventValue",
    "ExecutionMode",
]

print(f"ASTOCK Quant Engine v{__version__} initialized")


class EventFormat:
    """兼容性包装: 轻量级事件对象，提供 set_type/set/get/get_type/to_json 等方法"""
    def __init__(self):
        self._type = None
        self._attributes = {}

    def set_type(self, t: str):
        self._type = t

    def get_type(self) -> str:
        return self._type

    def set(self, key: str, value):
        self._attributes[key] = value

    def get(self, key: str, default=None):
        return self._attributes.get(key, default)

    @property
    def attributes(self):
        return dict(self._attributes)

    def to_json(self):
        try:
            import json
            payload = dict(self._attributes)
            payload['type'] = self._type
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            return '{}'

    def set_correlation_id(self, cid: str):
        self._attributes['correlation_id'] = cid

    def get_correlation_id(self):
        return self._attributes.get('correlation_id')

    def set_priority(self, p: int):
        self._attributes['priority'] = int(p)

    def get_priority(self):
        return self._attributes.get('priority')


class EventValue:
    """简单容器类型的别名/占位符"""
    def __init__(self, value=None):
        self.value = value
    # placeholder: no extra methods required


# 互操作兼容: ExecutionMode 枚举 (用于测试)
from enum import Enum as _Enum


class ExecutionMode(_Enum):
    SYNC = 'sync'
    ASYNC = 'async'

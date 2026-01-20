from setuptools import setup, find_packages, Extension
from setuptools.command.build_ext import build_ext
import sys
import subprocess

# 确保在Python 3.12下运行
if sys.version_info[:2] < (3, 12) or sys.version_info[:2] >= (3, 13):
    raise RuntimeError("本项目要求 Python 版本 >=3.12, <3.13")

# 定义一个辅助函数来获取Python 3.12的包含目录和库目录
def get_py312_paths():
    import sysconfig
    include_dir = sysconfig.get_path('include')
    # Windows 上库目录的特定获取方式
    if sys.platform == "win32":
        lib_dir = sysconfig.get_config_var('installed_base') + "\\libs"
    else:
        lib_dir = sysconfig.get_config_var('LIBDIR')
    return include_dir, lib_dir

include_dir, lib_dir = get_py312_paths()

ext_modules = [
    Extension(
        'quant_engine.fast_factors',
        sources=['bindings/fast_factors.cpp'],
        include_dirs=[include_dir, 'bindings/'],  # 显式指定Python 3.12的头文件路径
        library_dirs=[lib_dir],  # 显式指定Python 3.12的库路径
        # Windows 上需要链接 python312.lib
        libraries=['python312'] if sys.platform == "win32" else [],
        language='c++',
        extra_compile_args=['/std:c++17'] if sys.platform == "win32" else ['-std=c++17'],
    ),
]

setup(
    name="quant_engine",
    version="1.0.0",
    python_requires=">=3.12, <3.13",  # 明确版本范围
    ext_modules=ext_modules,
    # ... 其他设置
)
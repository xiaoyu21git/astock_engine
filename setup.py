from setuptools import setup, Extension, find_packages
import sys
import sysconfig
from pathlib import Path

# -------- Python 版本控制 --------
if not (3, 12) <= sys.version_info < (3, 13):
    raise RuntimeError("Requires Python >=3.12,<3.13")

ROOT = Path(__file__).parent.resolve()

# -------- Python include / lib --------
include_dir = sysconfig.get_path("include")

lib_dirs = []
libs = []
if sys.platform == "win32":
    lib_dirs.append(sysconfig.get_config_var("installed_base") + "\\libs")
    libs.append("python312")

# -------- 公共 C++ 编译参数 --------
COMMON_COMPILE_ARGS = (
    ["/std:c++17"] if sys.platform == "win32" else ["-std=c++17"]
)

# -------- C++ 扩展模块定义（集中管理） --------
def cpp_extension(name, sources):
    return Extension(
        name=name,
        sources=[str(ROOT / s) for s in sources],
        include_dirs=[
            include_dir,
            str(ROOT / "cpp"),
        ],
        library_dirs=lib_dirs,
        libraries=libs,
        language="c++",
        extra_compile_args=COMMON_COMPILE_ARGS,
    )

ext_modules = [
    cpp_extension(
        "quant_engine._native.fast_factors",
        ["bindings/fast_factors.cpp"],
    ),
    cpp_extension(
        "quant_engine._native.fast_factors",
        ["bindings/modules/EventCore/eventbus_binding.cpp"],
    ),
    # 新增 GlobalState pybind11 模块
    cpp_extension(
        "globalstate_native",
        ["../src/engine/src/GlobalState.cpp", "pybindings_globalstate.cpp"],
    ),
]

setup(
    name="quant_engine",
    version="1.0.0",
    python_requires=">=3.12,<3.13",
    package_dir={"": "python"},
    packages=find_packages("python"),
    ext_modules=ext_modules,
)

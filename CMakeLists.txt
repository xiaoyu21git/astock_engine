# astock_engine/CMakeLists.txt
cmake_minimum_required(VERSION 3.15)
project(astock_python)

if(NOT BUILD_PYTHON_EXTENSIONS)
    message(STATUS "Python extensions disabled")
    return()
endif()

message(STATUS "Building Python extensions with local Python installation")

# ==================== 检查Python ====================
if(NOT Python_FOUND)
    message(FATAL_ERROR "Python not found")
endif()

# ==================== 查找本机pybind11 ====================
# 方法1：通过Python包管理器查找
execute_process(
    COMMAND ${Python_EXECUTABLE} -c "
try:
    import pybind11
    print(pybind11.get_include())
except ImportError:
    print('PYBIND11_NOT_FOUND')
    "
    OUTPUT_VARIABLE PYBIND11_INCLUDE_PATH
    OUTPUT_STRIP_TRAILING_WHITESPACE
)

if(PYBIND11_INCLUDE_PATH STREQUAL "PYBIND11_NOT_FOUND")
    # 方法2：在常见路径中查找
    find_path(PYBIND11_INCLUDE_DIR
        NAMES pybind11/pybind11.h
        PATHS
            "C:/Python312/include/pybind11"  # Windows Python 3.12
            "C:/Python311/include/pybind11"  # Windows Python 3.11
            "C:/Python310/include/pybind11"  # Windows Python 3.10
            "C:/Python39/include/pybind11"   # Windows Python 3.9
            "C:/Python38/include/pybind11"   # Windows Python 3.8
            "${Python_SITELIB}/pybind11/include"
            "${Python_INCLUDE_DIRS}/pybind11"
            "/usr/include/pybind11"
            "/usr/local/include/pybind11"
        NO_DEFAULT_PATH
    )
    
    if(PYBIND11_INCLUDE_DIR)
        set(PYBIND11_INCLUDE_PATH ${PYBIND11_INCLUDE_DIR})
    else()
        message(WARNING "pybind11 not found. Creating minimal module...")
        set(USE_MINIMAL_MODULE TRUE)
    endif()
else()
    message(STATUS "Found pybind11 include path: ${PYBIND11_INCLUDE_PATH}")
    set(USE_MINIMAL_MODULE FALSE)
endif()

# ==================== 创建绑定源文件 ====================
if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/pybindings.cpp")
    file(WRITE "${CMAKE_CURRENT_SOURCE_DIR}/pybindings.cpp"
        "// ASTOCK Quant Engine Python Bindings\n"
        "#include <pybind11/pybind11.h>\n"
        "#include <pybind11/stl.h>\n"
        "\n"
        "namespace py = pybind11;\n"
        "\n"
        "// 测试函数\n"
        "int add(int a, int b) {\n"
        "    return a + b;\n"
        "}\n"
        "\n"
        "std::string greet(const std::string& name) {\n"
        "    return \"Hello from ASTOCK Engine, \" + name + \"!\";\n"
        "}\n"
        "\n"
        "// 获取引擎信息\n"
        "std::string get_engine_info() {\n"
        "    return \"ASTOCK Quant Engine v0.1.0\";\n"
        "}\n"
        "\n"
        "// 主模块\n"
        "PYBIND11_MODULE(_native, m) {\n"
        "    m.doc() = \"ASTOCK Quant Engine Python Bindings\";\n"
        "    \n"
        "    // 版本信息\n"
        "    m.attr(\"__version__\") = \"0.1.0\";\n"
        "    m.attr(\"__author__\") = \"ASTOCK Team\";\n"
        "    \n"
        "    // 绑定函数\n"
        "    m.def(\"add\", &add, \"Add two numbers\",\n"
        "          py::arg(\"a\"), py::arg(\"b\"));\n"
        "    \n"
        "    m.def(\"greet\", &greet, \"Greet someone\",\n"
        "          py::arg(\"name\"));\n"
        "    \n"
        "    m.def(\"get_engine_info\", &get_engine_info,\n"
        "          \"Get engine information\");\n"
        "    \n"
        "    // 时间戳函数\n"
        "    m.def(\"timestamp\", []() -> long long {\n"
        "        #include <chrono>\n"
        "        auto now = std::chrono::system_clock::now();\n"
        "        return std::chrono::duration_cast<std::chrono::milliseconds>(\n"
        "            now.time_since_epoch()).count();\n"
        "    }, \"Get current timestamp in milliseconds\");\n"
        "}\n"
    )
    message(STATUS "Created pybindings.cpp")
endif()

# ==================== 创建Python模块 ====================
if(USE_MINIMAL_MODULE)
    # 创建最小C扩展（不使用pybind11）
    message(STATUS "Creating minimal C extension (no pybind11)")
    
    add_library(astock_engine_native MODULE "${CMAKE_CURRENT_SOURCE_DIR}/minimal_module.c")
    
    # 创建最小C模块
    file(WRITE "${CMAKE_CURRENT_SOURCE_DIR}/minimal_module.c"
        "#include <Python.h>\n\n"
        "static PyObject* add(PyObject* self, PyObject* args) {\n"
        "    int a, b;\n"
        "    if (!PyArg_ParseTuple(args, \"ii\", &a, &b)) {\n"
        "        return NULL;\n"
        "    }\n"
        "    return PyLong_FromLong(a + b);\n"
        "}\n\n"
        "static PyObject* greet(PyObject* self, PyObject* args) {\n"
        "    const char* name;\n"
        "    if (!PyArg_ParseTuple(args, \"s\", &name)) {\n"
        "        return NULL;\n"
        "    }\n"
        "    char buffer[256];\n"
        "    snprintf(buffer, sizeof(buffer), \"Hello from ASTOCK Engine, %s!\", name);\n"
        "    return PyUnicode_FromString(buffer);\n"
        "}\n\n"
        "static PyMethodDef module_methods[] = {\n"
        "    {\"add\", add, METH_VARARGS, \"Add two integers\"},\n"
        "    {\"greet\", greet, METH_VARARGS, \"Greet someone\"},\n"
        "    {NULL, NULL, 0, NULL}\n"
        "};\n\n"
        "static struct PyModuleDef native_module = {\n"
        "    PyModuleDef_HEAD_INIT,\n"
        "    \"_native\",\n"
        "    \"ASTOCK Engine native module\",\n"
        "    -1,\n"
        "    module_methods\n"
        "};\n\n"
        "PyMODINIT_FUNC PyInit__native(void) {\n"
        "    return PyModule_Create(&native_module);\n"
        "}\n"
    )
else()
    # 使用pybind11创建模块
    message(STATUS "Creating pybind11 module")
    
    # 手动创建模块（不使用pybind11_add_module）
    add_library(astock_engine_native MODULE "${CMAKE_CURRENT_SOURCE_DIR}/pybindings.cpp")
endif()

# ==================== 设置模块属性 ====================
set_target_properties(astock_engine_native PROPERTIES
    PREFIX ""
    OUTPUT_NAME "_native"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)

# Windows特定的设置
if(WIN32)
    set_target_properties(astock_engine_native PROPERTIES
        SUFFIX ".pyd"
    )
else()
    set_target_properties(astock_engine_native PROPERTIES
        SUFFIX ".so"
    )
endif()

# ==================== 包含目录 ====================
target_include_directories(astock_engine_native PRIVATE
    ${Python_INCLUDE_DIRS}
    ${CMAKE_SOURCE_DIR}/src
)

# 添加pybind11头文件（如果找到）
if(NOT USE_MINIMAL_MODULE AND PYBIND11_INCLUDE_PATH)
    target_include_directories(astock_engine_native PRIVATE
        ${PYBIND11_INCLUDE_PATH}
    )
endif()

# ==================== 链接库 ====================
target_link_libraries(astock_engine_native PRIVATE
    astock_core
    ${Python_LIBRARIES}
)

# ==================== 编译定义 ====================
if(WIN32)
    target_compile_definitions(astock_engine_native PRIVATE
        _WINDLL
        _USRDLL
    )
endif()

# ==================== 创建__init__.py ====================
if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/__init__.py")
    file(WRITE "${CMAKE_CURRENT_SOURCE_DIR}/__init__.py"
        "\"\"\"\n"
        "ASTOCK Quant Engine Python Interface\n"
        "\"\"\"\n"
        "\n"
        "__version__ = \"0.1.0\"\n"
        "__author__ = \"ASTOCK Team\"\n"
        "\n"
        "# 尝试导入原生模块\n"
        "_has_native = False\n"
        "_native_method = \"unknown\"\n"
        "\n"
        "try:\n"
        "    from ._native import *\n"
        "    _has_native = True\n"
        "    _native_method = \"pybind11\"\n"
        "    print(f\"INFO: Native C++ extension loaded ({_native_method})\")\n"
        "except ImportError as e:\n"
        "    print(f\"INFO: Using Python implementation: {e}\")\n"
        "    \n"
        "    # Python回退实现\n"
        "    def add(a, b):\n"
        "        \"\"\"Add two numbers\"\"\"\n"
        "        return a + b\n"
        "    \n"
        "    def greet(name):\n"
        "        \"\"\"Greet someone\"\"\"\n"
        "        return f\"Hello from ASTOCK Engine, {name}!\"\n"
        "    \n"
        "    def get_engine_info():\n"
        "        \"\"\"Get engine information\"\"\"\n"
        "        return \"ASTOCK Quant Engine v0.1.0 (Python fallback)\"\n"
        "    \n"
        "    def timestamp():\n"
        "        \"\"\"Get current timestamp\"\"\"\n"
        "        import time\n"
        "        return int(time.time() * 1000)\n"
        "\n"
        "# 导出公共API\n"
        "__all__ = [\n"
        "    'add',\n"
        "    'greet',\n"
        "    'get_engine_info',\n"
        "    'timestamp',\n"
        "    '__version__',\n"
        "    '__author__',\n"
        "    '_has_native',\n"
        "    '_native_method'\n"
        "]\n"
    )
    message(STATUS "Created __init__.py")
endif()

message(STATUS "Python module will be built in: ${CMAKE_CURRENT_SOURCE_DIR}")
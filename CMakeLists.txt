cmake_minimum_required(VERSION 3.15)

# 强制 C++17 并为 MSVC 添加 /Zc:__cplusplus
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_compile_options("$<$<CXX_COMPILER_ID:MSVC>:/Zc:__cplusplus>")

# ==================== 开关 ====================
if(NOT BUILD_PYTHON_EXTENSIONS)
    message(STATUS "Python extensions disabled")
    return()
endif()

message(STATUS "Building Python extensions with local Python installation")

# ==================== 查找Python ====================
find_package(Python COMPONENTS Interpreter Development REQUIRED)

# ==================== 查找pybind11 ====================
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
    find_path(PYBIND11_INCLUDE_DIR
        NAMES pybind11/pybind11.h
        PATHS
            ${Python_INCLUDE_DIRS}/pybind11
            "/usr/include/pybind11"
            "/usr/local/include/pybind11"
        NO_DEFAULT_PATH
    )
    if(PYBIND11_INCLUDE_DIR)
        set(PYBIND11_INCLUDE_PATH ${PYBIND11_INCLUDE_DIR})
    else()
        message(FATAL_ERROR "pybind11 not found. Please install: pip install pybind11")
    endif()
else()
    message(STATUS "Found pybind11 include path: ${PYBIND11_INCLUDE_PATH}")
endif()

# ==================== 创建Python模块 ====================
add_library(astock_engine_native MODULE "${CMAKE_CURRENT_SOURCE_DIR}/pybindings.cpp")

# ==================== EventBus Python模块 ====================
add_library(eventbus_native MODULE "${CMAKE_CURRENT_SOURCE_DIR}/pybindings_eventbus_simple.cpp")

# 查找MySQL库（与 src/infrastructure/CMake 中保持一致，兼容 D: / C: 安装路径）
find_library(MYSQL_LIB
    NAMES libmysql mysqlclient
    PATHS
        "D:/Program Files/MySQL/lib"
        "D:/Program Files/MySQL/MySQL Server 8.0/lib"
        "C:/Program Files/MySQL/MySQL Server 8.0/lib"
        "C:/Program Files/MySQL/MySQL Connector C++ 8.0/lib64"
        "/usr/lib/x86_64-linux-gnu"
        "/usr/local/lib"
)

find_path(MYSQL_INCLUDE_DIR
    NAMES mysql.h mysql/mysql.h
    PATHS
        "D:/Program Files/MySQL/include"
        "D:/Program Files/MySQL/MySQL Server 8.0/include"
        "C:/Program Files/MySQL/MySQL Server 8.0/include"
        "C:/Program Files/MySQL/MySQL Connector C++ 8.0/include"
        "/usr/include/mysql"
        "/usr/local/include/mysql"
)

if(NOT MYSQL_LIB OR NOT MYSQL_INCLUDE_DIR)
    message(WARNING "MySQL not found. Database module will not be built.")
    message(STATUS "  MYSQL_LIB: ${MYSQL_LIB}")
    message(STATUS "  MYSQL_INCLUDE_DIR: ${MYSQL_INCLUDE_DIR}")
else()
    message(STATUS "Found MySQL: ${MYSQL_LIB}")
    message(STATUS "MySQL include: ${MYSQL_INCLUDE_DIR}")
endif()

# ==================== Database Python模块 ====================
# 查找Qt6（database_native 依赖的 infrastructure 使用了 Qt）
find_package(Qt6 COMPONENTS Core Sql QUIET)

# 仅当同时找到 MySQL 开发库且存在 infrastructure 目标时才构建
# database_native removed — pybindings_database.cpp deleted
# if(MYSQL_LIB AND MYSQL_INCLUDE_DIR AND TARGET infrastructure)
#     add_library(database_native MODULE "${CMAKE_CURRENT_SOURCE_DIR}/pybindings_database.cpp")
# endif()

# ==================== 模块属性 ====================
set_target_properties(astock_engine_native PROPERTIES
    PREFIX ""
    OUTPUT_NAME "_native"
    SUFFIX ".pyd"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/astock_engine"
)
target_compile_options(astock_engine_native PRIVATE $<$<CXX_COMPILER_ID:MSVC>:/permissive->)

set_target_properties(eventbus_native PROPERTIES
    PREFIX ""
    OUTPUT_NAME "eventbus_native"
)
target_compile_options(eventbus_native PRIVATE $<$<CXX_COMPILER_ID:MSVC>:/permissive->)

if(TARGET database_native)
    set_target_properties(database_native PROPERTIES
        PREFIX ""
        OUTPUT_NAME "database_native"
    )
    target_compile_options(database_native PRIVATE $<$<CXX_COMPILER_ID:MSVC>:/permissive->)
endif()

# ==================== 包含目录 ====================
target_include_directories(astock_engine_native PRIVATE
    ${Python_INCLUDE_DIRS}
    ${PYBIND11_INCLUDE_PATH}
)

target_include_directories(eventbus_native PRIVATE
    ${Python_INCLUDE_DIRS}
    ${PYBIND11_INCLUDE_PATH}
    ${CMAKE_SOURCE_DIR}/src/engine/include
)

if(TARGET database_native)
    target_include_directories(database_native PRIVATE
        ${Python_INCLUDE_DIRS}
        ${PYBIND11_INCLUDE_PATH}
        ${CMAKE_SOURCE_DIR}/src/infrastructure/include
        ${MYSQL_INCLUDE_DIR}
    )
endif()

# ==================== 链接库 ====================
target_link_libraries(astock_engine_native PRIVATE
    astock_core
    ${Python_LIBRARIES}
)

target_link_libraries(eventbus_native PRIVATE
    astock_core
    ${Python_LIBRARIES}
)

if(TARGET database_native)
    target_link_libraries(database_native PRIVATE
        infrastructure
        ${Python_LIBRARIES}
        ${MYSQL_LIB}
    )
    # 链接Qt库（infrastructure头文件依赖Qt）
    if(TARGET Qt6::Core AND TARGET Qt6::Sql)
        target_link_libraries(database_native PRIVATE Qt6::Core Qt6::Sql)
    endif()
endif()

# ==================== 编译定义 ====================
if(WIN32)
    target_compile_definitions(astock_engine_native PRIVATE _WINDLL _USRDLL)
    target_compile_definitions(eventbus_native PRIVATE _WINDLL _USRDLL)
    if(TARGET database_native)
        target_compile_definitions(database_native PRIVATE _WINDLL _USRDLL)
    endif()
endif()

message(STATUS "Python module will be built")
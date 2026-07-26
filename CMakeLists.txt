cmake_minimum_required(VERSION 3.15)

# 强制 C++17（/Zc:__cplusplus 已在根 CMakeLists.txt 全局设置）
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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

# ==================== Database Python模块 ====================
# database_native removed — pybindings_database.cpp deleted

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

# ==================== Debug: Python缺少debug库, 强制用release ====================
if(WIN32 AND CMAKE_BUILD_TYPE MATCHES "[Dd]ebug")
    set(Python_LIBRARIES "${Python_LIBRARY_RELEASE}")
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

# database_native target removed — see above

# ==================== 编译定义 ====================
if(WIN32)
    target_compile_definitions(astock_engine_native PRIVATE _WINDLL _USRDLL)
    target_compile_definitions(eventbus_native PRIVATE _WINDLL _USRDLL)
    if(TARGET database_native)
        target_compile_definitions(database_native PRIVATE _WINDLL _USRDLL)
    endif()
endif()

message(STATUS "Python module will be built")
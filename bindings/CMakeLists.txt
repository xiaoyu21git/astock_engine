# Python C++扩展
cmake_minimum_required(VERSION 3.15)

# 使用全局的Python设置
message(STATUS "构建Python扩展，Python版本: ${Python_VERSION}")

# 获取pybind11
include(FetchContent)
FetchContent_Declare(
    pybind11
    GIT_REPOSITORY https://github.com/pybind/pybind11.git
    GIT_TAG v2.11.1
)
FetchContent_MakeAvailable(pybind11)

# 定义Python模块
pybind11_add_module(fast_factors 
    fast_factors.cpp
    modules/market_data_module.cpp
)

# 链接Python库
target_link_libraries(fast_factors PRIVATE ${Python_LIBRARIES})

# 设置输出位置
set_target_properties(fast_factors PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin/astock_engine
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin/astock_engine
)

if(WIN32)
    set_target_properties(fast_factors PROPERTIES SUFFIX ".pyd")
endif()

# 安装
install(TARGETS fast_factors
    LIBRARY DESTINATION astock_engine
    RUNTIME DESTINATION astock_engine
)
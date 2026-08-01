# CMakeLists.txt — 轨道 A pybind11 / C++ Bridge 工程（Day4 骨架）
#
# 构建要求：
#   Python 3.10+（麒麟 V11 默认 3.12.3，见 Day1 基线）
#   pybind11（项目 venv 内安装：python -m pip install pybind11）
#   C++17 编译器（g++ 12.3.0）
#
# 构建步骤（麒麟 VM）：
#   cd cpp-bridge
#   python -m pip install pybind11
#   cmake -B build -Dpybind11_DIR=$(python -m pybind11 --cmakedir)
#   cmake --build build
#
# 产物：build/kylin_embedding*.so → 放入 python 导入路径

cmake_minimum_required(VERSION 3.15)
project(kylin_embedding_bridge LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# ── pybind11 ──
find_package(pybind11 CONFIG REQUIRED)

# ── 核心库（纯 C++，可单测） ──
add_library(embedding_bridge_core STATIC
  src/embedding_bridge.cpp
)
target_include_directories(embedding_bridge_core PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/include
  ${CMAKE_CURRENT_SOURCE_DIR}
)
# 静态库需支持 PIC，才能链接进 pybind11 共享模块
set_target_properties(embedding_bridge_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(embedding_bridge_core PUBLIC dl)

# ── Python 扩展模块 ──
pybind11_add_module(kylin_embedding
  src/py_module.cpp
)
target_link_libraries(kylin_embedding PRIVATE embedding_bridge_core)

# ── 测试 ──
enable_testing()
add_subdirectory(tests)

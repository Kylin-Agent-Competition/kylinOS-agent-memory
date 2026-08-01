# tests/CMakeLists.txt — 轨道 A Bridge 测试（Day4 骨架）

# 测试 1: C++ 层错误映射测试（不依赖麒麟 SDK，可在任何环境编译运行）
add_executable(test_bridge_errors
  test_bridge_errors.cpp
)
target_link_libraries(test_bridge_errors PRIVATE embedding_bridge_core)
add_test(NAME bridge_errors COMMAND test_bridge_errors)

# 测试 2: C++ 层符号加载失败路径（so 不存在 → ERR_SO_NOT_FOUND）
add_executable(test_bridge_so_not_found
  test_bridge_so_not_found.cpp
)
target_link_libraries(test_bridge_so_not_found PRIVATE embedding_bridge_core)
add_test(NAME bridge_so_not_found COMMAND test_bridge_so_not_found)

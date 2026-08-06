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

# 测试 3: 畸形 SDK 结果防御（P0-2）— 可控假 .so
# 编译 fake_sdk_malformed.c 为共享库，test_bridge_malformed 通过 argv[1] 引用它
add_library(fake_sdk_malformed SHARED
  fake_sdk_malformed.c
)
set_target_properties(fake_sdk_malformed PROPERTIES
  PREFIX ""
  OUTPUT_NAME "fake_sdk_malformed"
)
add_executable(test_bridge_malformed
  test_bridge_malformed.cpp
)
target_link_libraries(test_bridge_malformed PRIVATE embedding_bridge_core)
# 测试运行时把假 .so 路径作为参数传入
add_test(NAME bridge_malformed
  COMMAND test_bridge_malformed $<TARGET_FILE:fake_sdk_malformed>
)

# 测试 4: Bridge destroy 终态（P1-1）— 假 .so
add_executable(test_bridge_destroyed
  test_bridge_destroyed.cpp
)
target_link_libraries(test_bridge_destroyed PRIVATE embedding_bridge_core)
add_test(NAME bridge_destroyed
  COMMAND test_bridge_destroyed $<TARGET_FILE:fake_sdk_malformed>
)

# 测试 5: 失败恢复策略（P1-High/P1-3）— 假 .so
add_executable(test_bridge_failure_recovery
  test_bridge_failure_recovery.cpp
)
target_link_libraries(test_bridge_failure_recovery PRIVATE embedding_bridge_core)
add_test(NAME bridge_failure_recovery
  COMMAND test_bridge_failure_recovery $<TARGET_FILE:fake_sdk_malformed>
)

cmake_minimum_required(VERSION 3.16)

# L0 Mock 契约测试：协议编解码 + MemoryClient ↔ MockGateway

# 协议编解码单元测试（无事件循环，APPLESS）
add_executable(test_protocol_adapter
    ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
    test_protocol_adapter.cpp
)
target_link_libraries(test_protocol_adapter
    PRIVATE
        Qt5::Core
        Qt5::Test
)
target_include_directories(test_protocol_adapter
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_protocol_adapter
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME protocol_adapter
    COMMAND test_protocol_adapter
)

# MemoryClient ↔ MockGateway 契约测试（需要事件循环）
add_executable(test_memory_client_mock
    ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
    ${CMAKE_SOURCE_DIR}/src/memory_client.cpp
    mock_gateway_server.cpp
    test_memory_client_mock.cpp
)
target_link_libraries(test_memory_client_mock
    PRIVATE
        Qt5::Core
        Qt5::Network
        Qt5::Test
)
target_include_directories(test_memory_client_mock
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_memory_client_mock
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME memory_client_mock
    COMMAND test_memory_client_mock
)

# ============================================================================
# D5-C Demo Harness L0 测试（覆盖 Reviewer REWORK §A / §B / §C 主问题）
# 范围：
#   A. status=error 响应明确路由 failed 阶段（UNSUPPORTED_METHOD 不得显示 sent）
#   B. MemoryContext 按 memory_context.v1.json 契约解析，空/error/malformed 不产生伪注入
#   C. 独立 pending / Reset / Preview 事件缓存等运行正确性
# 重要说明：本测试仅为 memory-client Demo / Prototype 的 L0 契约验证，
#           不代表真实 AI Assistant Hook / Chat DB / ChatRecord 已接入。
# ============================================================================
add_executable(test_d5_vertical_link_demo
    ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
    ${CMAKE_SOURCE_DIR}/src/memory_client.cpp
    ${CMAKE_SOURCE_DIR}/src/view_models/memory_view_model.cpp
    mock_gateway_server.cpp
    test_d5_vertical_link_demo.cpp
)
target_link_libraries(test_d5_vertical_link_demo
    PRIVATE
        Qt5::Core
        Qt5::Network
        Qt5::Test
)
target_include_directories(test_d5_vertical_link_demo
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_d5_vertical_link_demo
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME d5_vertical_link_demo
    COMMAND test_d5_vertical_link_demo
)

# ============================================================================
# D7C 偏好编辑 L0 Mock 契约测试（preference.list/create/update/rollback/history）
# 范围：MemoryViewModel 偏好 IPC payload 形状 + 响应路由（preferenceItems /
#       preferenceHistory / lastPreferenceAction / 失败路径）。
# 注意：L0 Mock 契约验证，不代表麒麟宿主真实交互（L2 另行在 VM 验证）。
# ============================================================================
add_executable(test_d7c_preference_editor
    /src/protocol_adapter.cpp
    /src/memory_client.cpp
    /src/view_models/memory_view_model.cpp
    mock_gateway_server.cpp
    test_d7c_preference_editor.cpp
)
target_link_libraries(test_d7c_preference_editor
    PRIVATE
        Qt5::Core
        Qt5::Network
        Qt5::Test
)
target_include_directories(test_d7c_preference_editor
    PRIVATE
        /src
)
target_compile_definitions(test_d7c_preference_editor
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR=""
)
add_test(
    NAME d7c_preference_editor
    COMMAND test_d7c_preference_editor
)

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
    ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
    ${CMAKE_SOURCE_DIR}/src/memory_client.cpp
    ${CMAKE_SOURCE_DIR}/src/view_models/memory_view_model.cpp
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
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_d7c_preference_editor
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME d7c_preference_editor
    COMMAND test_d7c_preference_editor
)

# ============================================================================
# D6-C 多源 Adapter L0 测试（Tool / Manual Config / Behavior + 事件标识 + 独立 pending）
# 范围：
#   A. Tool Adapter 5 状态（success/partial/failure/cancelled/timeout）
#   B. Manual Config 5 用例（长期/临时/安全/敏感拦截×2）
#   C. Behavior Observe 4 用例（含 mapping_status=PENDING_C_CONFIRMATION）
#   D. 事件标识契约（retry_of_turn_id / stop_reason / 重复 turn_id / event_id 独立性）
#   E. 运行正确性（四 busy 独立 pending 不串台）
# ============================================================================
add_executable(test_d6c_multi_source_adapters
    ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
    ${CMAKE_SOURCE_DIR}/src/memory_client.cpp
    ${CMAKE_SOURCE_DIR}/src/view_models/memory_view_model.cpp
    mock_gateway_server.cpp
    test_d6c_multi_source_adapters.cpp
)
target_link_libraries(test_d6c_multi_source_adapters
    PRIVATE
        Qt5::Core
        Qt5::Network
        Qt5::Test
)
target_include_directories(test_d6c_multi_source_adapters
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_d6c_multi_source_adapters
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME d6c_multi_source_adapters
    COMMAND test_d6c_multi_source_adapters
)

# ============================================================================
# D8C 知识详情 / 冲突对比 / 生命周期状态 L0 Mock 契约测试
# （knowledge.detail / conflict.compare / lifecycle.status，候选方法 pending ADR）
# 范围：MemoryViewModel 三个候选 IPC payload 形状 + 响应路由 + 独立 pending +
#       空参数 / 未连接拒绝 / status=error 失败路径。
# 注意：L0 Mock 契约验证，不代表麒麟宿主真实交互（L2 另行在 VM 验证）。
# ============================================================================
add_executable(test_d8c_knowledge_conflict_lifecycle
    ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
    ${CMAKE_SOURCE_DIR}/src/memory_client.cpp
    ${CMAKE_SOURCE_DIR}/src/view_models/memory_view_model.cpp
    mock_gateway_server.cpp
    test_d8c_knowledge_conflict_lifecycle.cpp
)
target_link_libraries(test_d8c_knowledge_conflict_lifecycle
    PRIVATE
        Qt5::Core
        Qt5::Network
        Qt5::Test
)
target_include_directories(test_d8c_knowledge_conflict_lifecycle
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_d8c_knowledge_conflict_lifecycle
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME d8c_knowledge_conflict_lifecycle
    COMMAND test_d8c_knowledge_conflict_lifecycle
)

# ============================================================================
# D9C Memory Context 组装 L0 Mock 契约测试
# （context.assemble，候选方法 pending ADR）
# 范围：MemoryViewModel context.assemble payload 形状 + 响应路由 +
#       可解释字段投影（recall_sources / memory_types / conflict_hints /
#       uncertainty_hints）+ Token 预算校验 + 防伪 Context（injection=failed/
#       skipped 不产生伪 Context）+ 独立 pending + 空参数 / 未连接拒绝。
# 注意：L0 Mock 契约验证，不代表麒麟宿主真实交互（L2 另行在 VM 验证）。
# ============================================================================
add_executable(test_d9c_context_assemble
    ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
    ${CMAKE_SOURCE_DIR}/src/memory_client.cpp
    ${CMAKE_SOURCE_DIR}/src/view_models/memory_view_model.cpp
    mock_gateway_server.cpp
    test_d9c_context_assemble.cpp
)
target_link_libraries(test_d9c_context_assemble
    PRIVATE
        Qt5::Core
        Qt5::Network
        Qt5::Test
)
target_include_directories(test_d9c_context_assemble
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_d9c_context_assemble
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME d9c_context_assemble
    COMMAND test_d9c_context_assemble
)

# ============================================================================
# D10C 精准遗忘 L0 Mock 契约测试
# （forget.preview / forget.execute；候选方法 pending ADR）
# 范围：A. 模式互斥（SEC-FORGET-03 五值互斥）
#       B. Preview 投影（selection_hash / affected_count / credential_ttl_s
#          / resolved_target_ids / selector_cleared）
#       C. 状态机（idle→previewing→awaiting_confirmation→executing→completed）
#       D. Execute 漏删保护（v0.3/MEDIUM-03：executed != affected → failed）
#       E. 跨用户操作拒绝（C-D10 #3：响应 user_id 不匹配 → blocked=true）
#       F. Execute 必须基于成功 Preview（stage != awaiting_confirmation → 拒绝）
#       G. 独立 busy/pending / 未连接拒绝
#       H. UNSUPPORTED_METHOD / error → failed，无伪结果
#       I. full_reset 携带 target_* → 拒绝（Demo fail-closed）
#       J. Hard Delete Runtime fail-closed：错误不自动降级软删
# 注意：L0 Mock 契约验证，不代表麒麟宿主真实交互（L2 另行在 VM 验证）。
# ============================================================================
add_executable(test_d10c_forgetting
    ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
    ${CMAKE_SOURCE_DIR}/src/memory_client.cpp
    ${CMAKE_SOURCE_DIR}/src/view_models/memory_view_model.cpp
    mock_gateway_server.cpp
    test_d10c_forgetting.cpp
)
target_link_libraries(test_d10c_forgetting
    PRIVATE
        Qt5::Core
        Qt5::Network
        Qt5::Test
)
target_include_directories(test_d10c_forgetting
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_d10c_forgetting
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME d10c_forgetting
    COMMAND test_d10c_forgetting
)

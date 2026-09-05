cmake_minimum_required(VERSION 3.16)

# L0 Mock 契约测试：协议编解码 + MemoryClient ↔ MockGateway

# d11c_qml_load 需要 QGuiApplication + QQmlEngine/QQmlComponent +
# Qt Quick 运行时 import（D11DemoOrchestratorPage.qml 依赖
# QtQuick.Controls 2.12 / QtQuick.Layouts 1.12）。
# 环境若未安装 qtdeclarative5-dev / qtquickcontrols2-5-dev 及其运行时
# QML 模块（L0 CI 在修复 PR #116 前仅 qtbase5-dev），为避免
# target_link_libraries(Qt5::Qml/Quick/Gui) 阶段以 "IMPORTED target
# not found" 报错而让整套 tests CMake Configure 失败、其它 9 个
# ctest 目标也全部跳过，这里先显式 find_package 并在缺包时发 WARNING
# 且不注册该目标，保证其余 L0 契约测试仍可编译运行。
# 注意：Qt5::QuickControls2 是 QML import QtQuick.Controls 2.12 的
#       IMPORTED target 入口；若缺失则 QML plugin 不会注册到
#       QQmlEngine 的 import 路径，module "QtQuick.Controls" 找不到。
find_package(Qt5 5.12 QUIET COMPONENTS Gui Qml Quick QuickControls2)
set(D11C_QML_LOAD_AVAILABLE FALSE)
if(Qt5Gui_FOUND AND Qt5Qml_FOUND AND Qt5Quick_FOUND AND Qt5QuickControls2_FOUND)
    set(D11C_QML_LOAD_AVAILABLE TRUE)
endif()
if(NOT D11C_QML_LOAD_AVAILABLE)
    message(WARNING "d11c_qml_load L0 测试跳过：Qt5::Gui/Qt5::Qml/Qt5::Quick/"
                    "Qt5::QuickControls2 IMPORTED targets 缺失。请在构建环境安装 "
                    "qtdeclarative5-dev、qtquickcontrols2-5-dev 及对应运行时 QML "
                    "模块（qml-module-qtquick-controls2 等），以获得 Reviewer E "
                    "HIGH-01 的真实 QQmlComponent 加载验证。其余 9 个 L0 ctest "
                    "目标不受影响。")
endif()

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

# ============================================================================
# D11-C 同一虚拟机全功能联调 · E2E Orchestrator L0 Mock 契约测试
# 范围（A~F 共 13 用例）：
#   A. Step1 普通聊天：A1 三路原文隔离（D5）；A2 PostTurn 用 turn.finalized (ADR-010)
#   B. Step2 跨会话：B1 切换 sessionId 仍成功 + 独立 pending 不串台
#   C. Step3 Tool：C1 toolName 正确转发；C2 UNSUPPORTED_METHOD safeMessage 不含正文
#   D. Step4 知识+生命周期：D1 conflictCandidates 非空；D2 lifecycleItems 非空
#   E. Step5 精准遗忘：E1 Preview HIGH-01 selector 明文清除；E2 Execute completed+无漏删；E3 错误凭据 fail-closed
#   F. 编排器总体一致性：F1 未连接 fail-closed；F2 5 步完毕 busy=false + stage 一致；F3 Reset 清 pending 防 stale response 回写
# 注意：L0 Mock 契约验证，不代表麒麟宿主真实交互（L2 由 B/D 轨在 D11B VM 复测归档）。
# ============================================================================
add_executable(test_d11c_e2e_orchestrator
    ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
    ${CMAKE_SOURCE_DIR}/src/memory_client.cpp
    ${CMAKE_SOURCE_DIR}/src/view_models/memory_view_model.cpp
    mock_gateway_server.cpp
    test_d11c_e2e_orchestrator.cpp
)
target_link_libraries(test_d11c_e2e_orchestrator
    PRIVATE
        Qt5::Core
        Qt5::Network
        Qt5::Test
)
target_include_directories(test_d11c_e2e_orchestrator
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_d11c_e2e_orchestrator
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME d11c_e2e_orchestrator
    COMMAND test_d11c_e2e_orchestrator
)

# ============================================================================
# D11-C QML 真实加载验证 L0 测试（Reviewer E HIGH-01 修复）
# 范围：QQuickView + QQmlEngine 真实加载 resources.qrc 内的
#       D11DemoOrchestratorPage.qml，验证 QML parser 可解析、alias 正确、
#       重复实例化无泄漏、Step Card implicitHeight > 0；替代原有只验证
#       qrc 打包的 smoke build。
# 注意：headless 运行（QT_QPA_PLATFORM=offscreen + QT_QUICK_BACKEND=software），
#       由 set_tests_properties ENVIRONMENT 和 CI workflow env 双重保障；
#       不代表真实 Runtime + D11B VM 已接线（L2 另行归档）。
# 环境保护：仅当 Qt5::Gui/Qml/Quick IMPORTED target 可发现时才注册，
#           缺包时发 WARNING 并跳过，避免其余 L0 目标因 Configure
#           失败而全部不编译。
# ============================================================================
if(D11C_QML_LOAD_AVAILABLE)
    # d11c_qml_load 需要 D11 QML 页面能在运行时通过 qrc:/ URL 被
    # QQmlComponent 解析。由于 ctest profile 是 -DBUILD_QML_APP=OFF，
    # 顶层 CMakeLists 里的 qt5_add_resources 仅把 resources.qrc 编进
    # kylin_memory_client_app 这个可执行文件，不会出现在 L0 测试
    # 可执行文件里。
    #
    # 解决：显式使用 qt5_add_resources 宏把 <top>/qml/resources.qrc
    # 编译成 qrc_resources.cpp 并加入测试 target 源文件列表。
    # 相对于依赖 CMAKE_AUTORCC 自动处理 .qrc 源文件，显式调用
    # qt5_add_resources() 更稳定：
    #   * AUTORCC 对绝对路径的 .qrc 文件在部分 CMake 版本/CI 平台
    #     上会静默跳过（Qt5CoreMacros 内的依赖探测失败）；
    #   * qt5_add_resources 直接调用 Qt 安装的 rcc 二进制，生成的
    #     源文件明明白白地参与 target 编译，不会出 bug。
    qt5_add_resources(D11C_QML_LOAD_RCC_SOURCES
        "${CMAKE_SOURCE_DIR}/qml/resources.qrc"
    )

    add_executable(test_d11c_qml_load
        ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
        ${CMAKE_SOURCE_DIR}/src/memory_client.cpp
        ${CMAKE_SOURCE_DIR}/src/view_models/memory_view_model.cpp
        mock_gateway_server.cpp
        test_d11c_qml_load.cpp
        ${D11C_QML_LOAD_RCC_SOURCES}
    )
    target_link_libraries(test_d11c_qml_load
        PRIVATE
            Qt5::Core
            Qt5::Gui
            Qt5::Network
            Qt5::Qml
            Qt5::Quick
            # QtQuick.Controls 2.12 IMPORTED target：用于在 C++ 侧
            # 触发 QQuickStyle plugin 的静态初始化，并确保
            # QtQuick.Controls.2/qmldir 所在路径被添加到 QQmlEngine
            # 默认 import 路径中；缺少则 QML import QtQuick.Controls
            # 时一律报 "module not found"。
            Qt5::QuickControls2
            Qt5::Test
    )
    target_include_directories(test_d11c_qml_load
        PRIVATE
            ${CMAKE_SOURCE_DIR}/src
    )
    target_compile_definitions(test_d11c_qml_load
        PRIVATE
            QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
    )
    add_test(
        NAME d11c_qml_load
        COMMAND test_d11c_qml_load
    )
    # CI headless 环境没有 X11 / display server，QGuiApplication 在 main()
    # 阶段（由 QTEST_MAIN 生成）尝试加载 xcb 平台插件会以
    # "could not connect to display" 直接 abort（先于 test 内
    # initTestCase 的 qputenv 执行）。
    # set_tests_properties ENVIRONMENT 在进程启动前设置环境变量，
    # QGuiApplication 构造时即可命中 offscreen 平台插件；
    # CI workflow 的 env 也是同值备份。
    #
    # QT_QUICK_BACKEND=software：QQuickItem（D11 顶层是 ScrollView）
    # create() 时 Qt Quick SceneGraph 会尝试初始化默认的 OpenGL backend；
    # 即便 QT_QPA_PLATFORM=offscreen，offscreen 平台的 GL context 也
    # 可能加载失败，导致 QQuickView 加载阶段 SIGSEGV (signal 11)。
    # 开启 software backend（Qt Quick 2D adaption）即可在无 GPU / 无
    # EGL 的 L0 CI runner 上安全完成 QQuickItem 实例化。
    set_tests_properties(d11c_qml_load PROPERTIES
        ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software"
    )
endif()

# ============================================================================
# D13-C 端到端会话评测 · 主演示稳定性复测 L0 Mock 契约测试
# 范围（S1~S6 共 6 个稳定性 test slot）：
#   S1. 主演示编排复跑 5 轮稳定性（无 hang、无 stage 错乱、安全护栏通过）
#   S2. PostTurn stop_reason 透传语义（stop/length/content_filter/tool_use）
#   S3. retry_of_turn_id 透传 + 非 retry 必须为空
#   S4. 客户端 5000ms deadline timeout fail-closed（无死锁、可恢复）
#   S5. 跨会话隔离复跑（A/B session 反复切换，injectedContextText 严格区分）
#   S6. Reset 清 pending 防 stale response 回写（toolStage 保持 idle）
# 注意：L0 Mock 契约验证，不代表麒麟宿主真实交互（L2 由 B/D 轨另行归档）。
# ============================================================================
add_executable(test_d13c_stability
    ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
    ${CMAKE_SOURCE_DIR}/src/memory_client.cpp
    ${CMAKE_SOURCE_DIR}/src/view_models/memory_view_model.cpp
    mock_gateway_server.cpp
    test_d13c_stability.cpp
)
target_link_libraries(test_d13c_stability
    PRIVATE
        Qt5::Core
        Qt5::Network
        Qt5::Test
)
target_include_directories(test_d13c_stability
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_d13c_stability
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME d13c_stability
    COMMAND test_d13c_stability
)

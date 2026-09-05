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

    # ========================================================================
    # 全 QML 文件编译加载 L0 回归（PR151 麒麟 VM 回归配套）
    #
    # 背景：VerticalLinkPage.qml 的 ColumnLayout padding（QtQuick.Layouts
    # padding 自 Qt 5.15 起才有）在麒麟 VM（Qt 5.12）加载即失败（退出码
    # 255），而 CI（Qt 5.15）全绿——d11c_qml_load 仅覆盖 D11 页面，
    # 其余 QML 文件无加载覆盖。本目标对 qrc 内全部 14 个 QML 文件做
    # QQmlComponent status==Ready 验证，堵住编译期回归盲区。
    # 已知局限：Qt 版本特性差异（5.12 vs 5.15）仍需麒麟 VM L2 回归确认。
    # ========================================================================
    add_executable(test_qml_pages_load
        ${CMAKE_SOURCE_DIR}/src/protocol_adapter.cpp
        ${CMAKE_SOURCE_DIR}/src/memory_client.cpp
        ${CMAKE_SOURCE_DIR}/src/view_models/memory_view_model.cpp
        test_qml_pages_load.cpp
        ${D11C_QML_LOAD_RCC_SOURCES}
    )
    target_link_libraries(test_qml_pages_load
        PRIVATE
            Qt5::Core
            Qt5::Gui
            Qt5::Network
            Qt5::Qml
            Qt5::Quick
            Qt5::QuickControls2
            Qt5::Test
    )
    target_include_directories(test_qml_pages_load
        PRIVATE
            ${CMAKE_SOURCE_DIR}/src
    )
    add_test(
        NAME qml_pages_load
        COMMAND test_qml_pages_load
    )
    set_tests_properties(qml_pages_load PROPERTIES
        ENVIRONMENT "QT_QPA_PLATFORM=offscreen;QT_QUICK_BACKEND=software"
    )
endif()

# ============================================================================
# Host mapping 任务卡 S1 — TurnExtractionAdapter 骨架 L0 契约测试
# （纯内存 resolver；生产 resolver 属 S2，BLOCKED_BY_HOST_MAPPING 不变）
# 范围（事件契约 v1 §7 五边界，A~F 共 13 用例）：
#   A. 元数据与关联：ipcEvent 字段完整（无正文）+ source_event_id 关联 +
#      occurred_at 透传/回退
#   B. 原文隔离红线：正文只在 providerCandidate，ipcEvent 序列化全文不含正文 +
#      source_reference 生成规则
#   C. fail-closed：resolver 未命中 / 命中但空串 / 未注入 resolver
#      → 候选无正文、safeError 固定安全消息（不含引用/正文）
#   D. tool_results 组装：受控 Tool resolver 命中组装 / 未命中不编造（上抛）/
#      无调用空数组
#   E. 纯内存测试 resolver 注册-解析往返
#   F. 事件标识一致性：同 (session,turn) idempotency_key 一致 + event_id 每次新
# 注意：本测试仅为 memory-client 侧 S1 骨架的 L0 契约验证（纯内存 resolver），
#       不声称真实 AI Assistant Hook / Chat DB / 正文通道已接入。
# ============================================================================
add_executable(test_turn_extraction_adapter
    ${CMAKE_SOURCE_DIR}/src/adapters/turn_extraction_adapter.cpp
    test_turn_extraction_adapter.cpp
)
target_link_libraries(test_turn_extraction_adapter
    PRIVATE
        Qt5::Core
        Qt5::Test
)
target_include_directories(test_turn_extraction_adapter
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_turn_extraction_adapter
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME turn_extraction_adapter
    COMMAND test_turn_extraction_adapter
)

# ============================================================================
# Host mapping 任务卡 S2 — ProductionSourceResolver L0 契约测试
# （fixture SQLite 模拟宿主 Chat DB；生产注册仍 BLOCKED_BY_HOST_MAPPING）
# 范围（A~D 共 14 用例）：
#   A. 只读打开与命中：open 成功 / resolve 命中（originalUserText+
#      modelResponse，modelRequest 不编造）/ 与 TurnExtractionAdapter
#      集成（Extracted + 正文仅入 providerCandidate，原文隔离红线）
#   B. 只读红线：chmod 0444 仍可打开命中（证明 QSQLITE_OPEN_READONLY
#      生效）/ resolve 前后 DB 文件 SHA-256 不变（绝不写宿主 DB）
#   C. fail-closed：未 open / 文件不存在 / chmod 000 / 表缺失 / 行缺失 /
#      同 turn 无用户消息 / 用户正文空串 / 终稿非 assistant 角色 /
#      非受控引用格式（7 种）/ config 标识符非法（SQL 注入防御）
#   D. schema 适配：自定义表/列/角色值命中（VM 确认真实 schema 后
#      经 config 覆盖，不改代码）
# 运行依赖：Qt5 Sql QSQLITE 运行时驱动插件（Debian/Ubuntu:
#   libqt5sql5-sqlite，CI workflow 已安装；qtbase5-dev 的 Depends
#   libqt5sql5 仅提供链接库，不含 sqlite 驱动插件）。缺失时本测试
#   失败而非跳过——L0 全绿必须意味着只读/fail-closed 行为真实验证。
# 注意：本测试仅为 S2 生产 resolver 的 L0 契约验证（fixture SQLite），
#       不声称真实宿主 Chat DB 已接入。
# ============================================================================
add_executable(test_production_source_resolver
    ${CMAKE_SOURCE_DIR}/src/adapters/production_source_resolver.cpp
    ${CMAKE_SOURCE_DIR}/src/adapters/turn_extraction_adapter.cpp
    test_production_source_resolver.cpp
)
target_link_libraries(test_production_source_resolver
    PRIVATE
        Qt5::Core
        Qt5::Sql
        Qt5::Test
)
target_include_directories(test_production_source_resolver
    PRIVATE
        ${CMAKE_SOURCE_DIR}/src
)
target_compile_definitions(test_production_source_resolver
    PRIVATE
        QT_TESTCLIENT_SOURCE_DIR="${CMAKE_SOURCE_DIR}"
)
add_test(
    NAME production_source_resolver
    COMMAND test_production_source_resolver
)

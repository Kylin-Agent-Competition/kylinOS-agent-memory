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

cmake_minimum_required(VERSION 3.16)

project(kylin_memory_client LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

if(MSVC)
    add_compile_options(/utf-8 /W4 /permissive-)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

option(KYLIN_MEMORY_CLIENT_BUILD_QML_APP "Build the QML GUI application (requires Qt Quick)" ON)
option(KYLIN_MEMORY_CLIENT_BUILD_TESTS "Build L0 mock contract tests" ON)

find_package(Qt5 5.12 REQUIRED COMPONENTS Core Network)

# ── memory-client 静态库（self-contained on QJsonObject，不依赖 contract v1） ──
add_library(kylin_memory_client STATIC
    src/protocol_adapter.cpp
    src/memory_client.cpp
    src/adapters/turn_extraction_adapter.cpp
    src/view_models/memory_view_model.cpp
)

target_include_directories(kylin_memory_client
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/src
)

# QLocalSocket/QLocalServer 属于 Qt Network 模块
target_link_libraries(kylin_memory_client
    PUBLIC
        Qt5::Core
        Qt5::Network
)

# ── QML GUI 应用（可选，需要 Qt Quick） ──
if(KYLIN_MEMORY_CLIENT_BUILD_QML_APP)
    find_package(Qt5 5.12 REQUIRED COMPONENTS Gui Qml Quick QuickControls2)
    qt5_add_resources(QML_QRC_FILES
        qml/resources.qrc
    )
    add_executable(kylin_memory_client_app
        src/main.cpp
        ${QML_QRC_FILES}
    )
    target_link_libraries(kylin_memory_client_app
        PRIVATE
            kylin_memory_client
            Qt5::Gui
            Qt5::Qml
            Qt5::Quick
            Qt5::QuickControls2
    )
    set_target_properties(kylin_memory_client_app PROPERTIES
        OUTPUT_NAME kylin-memory-client
    )
endif()

# ── L0 Mock 契约测试 ──
if(KYLIN_MEMORY_CLIENT_BUILD_TESTS)
    enable_testing()
    find_package(Qt5 5.12 REQUIRED COMPONENTS Test)
    add_subdirectory(tests)
endif()

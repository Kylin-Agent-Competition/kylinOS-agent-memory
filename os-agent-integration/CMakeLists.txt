cmake_minimum_required(VERSION 3.16)

project(kylin_os_agent_memory_contract LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_AUTOMOC ON)

if(MSVC)
    add_compile_options(/utf-8 /W4 /permissive-)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

include(CTest)

find_package(Qt5 5.12 REQUIRED COMPONENTS Core)

add_library(os_agent_memory_contract_v1 STATIC
    contracts/memory_event_contract_v1.cpp
)

target_include_directories(os_agent_memory_contract_v1
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(os_agent_memory_contract_v1
    PUBLIC
        Qt5::Core
)

if(BUILD_TESTING)
    find_package(Qt5 5.12 REQUIRED COMPONENTS Test)

    add_executable(test_memory_event_contract_v1
        tests/test_memory_event_contract_v1.cpp
    )

    target_link_libraries(test_memory_event_contract_v1
        PRIVATE
            os_agent_memory_contract_v1
            Qt5::Test
    )

    target_compile_definitions(test_memory_event_contract_v1
        PRIVATE
            CONTRACT_EXAMPLE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/contracts/examples"
    )

    add_test(
        NAME memory_event_contract_v1
        COMMAND test_memory_event_contract_v1
    )
endif()

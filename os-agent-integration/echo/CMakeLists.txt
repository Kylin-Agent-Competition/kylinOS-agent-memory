cmake_minimum_required(VERSION 3.16)
project(kylin-memory-echo VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---- Echo Client (POSIX, no Qt required) ----
add_executable(echo_client echo_client.cpp)
target_compile_options(echo_client PRIVATE -Wall -Wextra -O2)

# ---- Kaiming Memory Client (POSIX, no Qt required) ----
add_executable(kaiming_memory_client kaiming_memory_client.cpp)
target_compile_options(kaiming_memory_client PRIVATE -Wall -Wextra -O2)

# ---- 可选的 Qt 版本 (需要 Qt5::Network) ----
# find_package(Qt5 COMPONENTS Network QUIET)
# if(Qt5Network_FOUND)
#     add_executable(echo_client_qt echo_client.cpp)
#     target_compile_definitions(echo_client_qt PRIVATE QLOCALSOCKET_AVAILABLE)
#     target_link_libraries(echo_client_qt PRIVATE Qt5::Network)
# endif()

# ---- 安装规则 ----
install(TARGETS echo_client kaiming_memory_client
    RUNTIME DESTINATION bin
    PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE
                GROUP_READ GROUP_EXECUTE
                WORLD_READ WORLD_EXECUTE
)

install(PROGRAMS memory_echo_server.py
    DESTINATION bin
    RENAME kylin-memory-echo-server
)

install(FILES
    kysec_authorize.sh
    test_rollback.sh
    DESTINATION share/kylin-memory-echo
    PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE
                GROUP_READ GROUP_EXECUTE
                WORLD_READ WORLD_EXECUTE
)
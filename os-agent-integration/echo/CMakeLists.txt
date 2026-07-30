cmake_minimum_required(VERSION 3.10)
project(kylin-memory-echo LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Qt5 依赖（麒麟 V11 默认 Qt 5）
find_package(Qt5 COMPONENTS Core Network REQUIRED)

add_executable(echo_client echo_client.cpp)
target_link_libraries(echo_client Qt5::Core Qt5::Network)
cmake_minimum_required(VERSION 3.16)
project(kylin-connect-hook VERSION 1.0.0 LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

find_package(Threads REQUIRED)

# ---- LD_PRELOAD connect() hook shared library ----
add_library(connect_hook SHARED libconnect_hook.c)
target_compile_options(connect_hook PRIVATE -Wall -Wextra -O2 -fvisibility=hidden)
target_link_libraries(connect_hook PRIVATE dl Threads::Threads)

# Strip symbols for smaller .so (optional, comment out if debugging needed)
# set_target_properties(connect_hook PROPERTIES LINK_FLAGS "-Wl,-s")

# ---- 安装规则 (部署到 ~/kylin-memory-echo/lib/) ----
install(TARGETS connect_hook
    LIBRARY DESTINATION lib/kylin-memory-echo
    PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE
                GROUP_READ GROUP_EXECUTE
                WORLD_READ WORLD_EXECUTE
)
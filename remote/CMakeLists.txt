cmake_minimum_required(VERSION 3.16)
project(jmx CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_compile_options(-Wall -Wextra -O2)

add_executable(jmxd src/jmxd.cpp)
target_include_directories(jmxd PRIVATE src)

add_executable(jmx src/jmx.cpp)
target_include_directories(jmx PRIVATE src)

add_executable(jmxcleanerd src/jmxcleanerd.cpp)
target_include_directories(jmx PRIVATE src)

install(TARGETS jmxcleanerd jmxd jmx RUNTIME DESTINATION bin)

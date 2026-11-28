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
target_include_directories(jmxcleanerd PRIVATE src)

enable_testing()
add_executable(remote_tests tests/remote_tests.cpp)
target_include_directories(remote_tests PRIVATE src)
add_test(NAME remote_tests COMMAND remote_tests)

# Build against the oldest supported Ubuntu release (see release workflow).
# Static-linking the C++ runtime keeps the package usable across distro
# versions without pinning libstdc++ versions in the Debian metadata.
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
  target_link_options(jmx PRIVATE -static-libstdc++ -static-libgcc)
  target_link_options(jmxd PRIVATE -static-libstdc++ -static-libgcc)
  target_link_options(jmxcleanerd PRIVATE -static-libstdc++ -static-libgcc)
endif()

install(TARGETS jmxcleanerd jmxd jmx RUNTIME DESTINATION bin)

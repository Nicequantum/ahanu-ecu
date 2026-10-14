cmake_minimum_required(VERSION 3.16)
project(grok_pilot_envelope CXX)
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# Match firmware constraints: no exceptions/RTTI in the module; strict FP for bit-exact parity with Python.
set(ENVELOPE_FLAGS -Wall -Wextra -Werror -ffp-contract=off -fno-fast-math)

find_package(GTest REQUIRED)
enable_testing()

# Compile-only check of the header under firmware-like flags.
add_library(envelope_firmware_check OBJECT test/firmware_flags_check.cpp)
target_include_directories(envelope_firmware_check PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_options(envelope_firmware_check PRIVATE ${ENVELOPE_FLAGS} -fno-exceptions -fno-rtti)

add_executable(envelope_tests test/test_envelope.cpp test/test_vectors.cpp)
target_include_directories(envelope_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_options(envelope_tests PRIVATE ${ENVELOPE_FLAGS})
target_compile_definitions(envelope_tests PRIVATE
  ENVELOPE_VECTORS_PATH="${CMAKE_CURRENT_SOURCE_DIR}/../../tests/vectors/envelope_vectors.txt")
target_link_libraries(envelope_tests PRIVATE GTest::gtest_main)
include(GoogleTest)
gtest_discover_tests(envelope_tests)

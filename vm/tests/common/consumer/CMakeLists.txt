cmake_minimum_required(VERSION 3.20)
project(frame_installed_consumer C)
find_package(qjs CONFIG REQUIRED)
find_package(quickjs-turbo CONFIG REQUIRED)
enable_testing()
add_executable(interpreter-installed-consumer main.c)
target_link_libraries(interpreter-installed-consumer PRIVATE quickjs-turbo::qjs)
add_test(NAME installed-public-api COMMAND interpreter-installed-consumer)
include(CheckLanguage)
check_language(CXX)
if(CMAKE_CXX_COMPILER)
    enable_language(CXX)
    add_executable(interpreter-installed-consumer-cxx cxx_consumer.cc)
    set_target_properties(
        interpreter-installed-consumer-cxx
        PROPERTIES CXX_STANDARD 11
                   CXX_STANDARD_REQUIRED ON
                   CXX_EXTENSIONS OFF)
    target_link_libraries(interpreter-installed-consumer-cxx PRIVATE qjs)
    add_test(NAME installed-public-api-cxx11 COMMAND interpreter-installed-consumer-cxx)
endif()
if(FRAME_NATIVE_TEST_SOURCE)
    if(FRAME_NATIVE_UNWIND_FILE)
        set(consumer_unwind_src "${FRAME_NATIVE_UNWIND_FILE}")
    else()
        set(consumer_unwind_src "${FRAME_NATIVE_TEST_SOURCE}/tests/common/native_promise_oom.c")
    endif()
    add_executable(interpreter-installed-unwind "${consumer_unwind_src}")
    target_include_directories(
        interpreter-installed-unwind PRIVATE "${FRAME_NATIVE_TEST_SOURCE}"
                                             "${FRAME_NATIVE_TEST_SOURCE}/tests/common")
    target_link_libraries(interpreter-installed-unwind PRIVATE qjs)
    add_test(NAME installed-native-unwind COMMAND interpreter-installed-unwind)
endif()

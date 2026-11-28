# Reuse the complete SysV x86-64 native test matrix (excluding ELF-only tool checks).
set(qjs_linux_abi_dir "${qjs_macos_abi_dir}")
include("${CMAKE_CURRENT_LIST_DIR}/../linux/InterpreterTests.cmake")

add_test(NAME macos-x86-macho-policy
         COMMAND "${Python3_EXECUTABLE}" -B
                 "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/macos/test_macho_x86.py")

add_executable(macos-x86-cvm-unwind "${CMAKE_CURRENT_SOURCE_DIR}/tests/x86/macos/test_cvm_unwind.c")
target_link_libraries(macos-x86-cvm-unwind PRIVATE qjs)
add_test(NAME macos-x86-cvm-unwind COMMAND macos-x86-cvm-unwind)

# Standalone foundation only. Do not set QJS_ENABLE_INTERP_FRAME or route qjs
# through these bridges until an actual AArch64 register VM is qualified.
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux"
   OR NOT CMAKE_C_COMPILER_ID STREQUAL "GNU"
   OR CMAKE_C_COMPILER_VERSION VERSION_LESS 13
   OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "AArch64 ABI checks require Linux LP64 and GCC 13+")
endif()
if(NOT QJS_FRAME_BUILD_TESTS
   OR NOT QJS_BACKPORT_CONTEXT_OOM
   OR NOT QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "PORTABLE"
   OR BUILD_SHARED_LIBS)
    message(
        FATAL_ERROR
            "AArch64 foundation checks require PORTABLE, static qjs, tests and declared core overlays"
    )
endif()
if(QJS_ENABLE_ASAN
   OR QJS_ENABLE_MSAN
   OR QJS_ENABLE_TSAN
   OR QJS_ENABLE_UBSAN
   OR CMAKE_INTERPROCEDURAL_OPTIMIZATION)
    message(
        FATAL_ERROR "AArch64 foundation currently qualifies ordinary non-LTO, nonsanitized builds")
endif()
include(CheckCSourceCompiles)
unset(QJS_AARCH64_ABI_TARGET CACHE)
check_c_source_compiles(
    "#if !defined(__aarch64__) || !defined(__linux__) || !defined(__LP64__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__\n#error Linux AArch64 LE LP64 required\n#endif\nint main(void) { return 0; }"
    QJS_AARCH64_ABI_TARGET)
if(NOT QJS_AARCH64_ABI_TARGET)
    message(FATAL_ERROR "AArch64 ABI checks require an actual AArch64 LE LP64 compiler target")
endif()
if(CMAKE_VERSION VERSION_LESS 3.20)
    message(FATAL_ERROR "AArch64 ABI checks require CMake 3.20+")
endif()
enable_language(ASM)
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
if(NOT CMAKE_READELF)
    find_program(CMAKE_READELF NAMES aarch64-linux-gnu-readelf REQUIRED)
endif()
set(qjs_arm_abi "${CMAKE_CURRENT_BINARY_DIR}/generated/aarch64-abi")
file(
    GLOB_RECURSE
    qjs_arm_abi_inputs
    CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/*.S"
    "${CMAKE_CURRENT_SOURCE_DIR}/asm/arm64/*.inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/arm64/linux/abi/*"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/*.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/*")
add_custom_command(
    OUTPUT "${qjs_arm_abi}/LAYOUT.json" "${qjs_arm_abi}/qjs-aarch64-abi-values.h"
           "${qjs_arm_abi}/qjs-aarch64-call-types.h"
    BYPRODUCTS "${qjs_arm_abi}/layout-probe.c" "${qjs_arm_abi}/layout-probe.o"
    COMMAND
        "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/verify/measure_abi.py"
        --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}" --output
        "${qjs_arm_abi}"
    DEPENDS qjs
            ${qjs_arm_abi_inputs}
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/elf64.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/tools/common/elf/layout_input.py"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/common/internal/abi/core-fields.json"
            "${CMAKE_CURRENT_BINARY_DIR}/generated/backports/BACKPORTS.json"
            "${CMAKE_BINARY_DIR}/compile_commands.json"
    VERBATIM)
add_custom_target(
    qjs-aarch64-abi-contract
    DEPENDS "${qjs_arm_abi}/LAYOUT.json" "${qjs_arm_abi}/qjs-aarch64-abi-values.h"
            "${qjs_arm_abi}/qjs-aarch64-call-types.h")
add_library(qjs-aarch64-call-abi OBJECT asm/arm64/linux/call-abi.S)
add_dependencies(qjs-aarch64-call-abi qjs-aarch64-abi-contract)
target_include_directories(qjs-aarch64-call-abi PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
                                                        "${QJS_UPSTREAM_DIR}" "${qjs_arm_abi}")
foreach(mode normal bad_saved)
    add_executable(
        interpreter-aarch64-abi-${mode}
        tests/arm64/call-abi.c tests/arm64/call-reference.c tests/arm64/callee-saved.S
        $<TARGET_OBJECTS:qjs-aarch64-call-abi>)
    add_dependencies(interpreter-aarch64-abi-${mode} qjs-aarch64-abi-contract)
    target_include_directories(
        interpreter-aarch64-abi-${mode} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${QJS_UPSTREAM_DIR}"
                                                "${qjs_arm_abi}")
    target_compile_options(
        interpreter-aarch64-abi-${mode}
        PRIVATE
            "$<$<COMPILE_LANGUAGE:C>:-O2;-g;-fno-omit-frame-pointer;-fasynchronous-unwind-tables>")
    target_link_options(interpreter-aarch64-abi-${mode} PRIVATE -pie -Wl,-z,noexecstack)
    target_link_libraries(interpreter-aarch64-abi-${mode} PRIVATE qjs)
endforeach()
target_compile_definitions(interpreter-aarch64-abi-bad_saved PRIVATE PROBE_BAD_SAVED=1)
add_test(NAME interpreter-aarch64-call-abi COMMAND interpreter-aarch64-abi-normal)
set_tests_properties(
    interpreter-aarch64-call-abi
    PROPERTIES
        PASS_REGULAR_EXPRESSION
        "AARCH64_CALL_ABI_OK JSValue=16 align=8 routes=5 reference=5 saved=10 unwind=3 reentry=2")
add_test(
    NAME interpreter-aarch64-saved-negative
    COMMAND
        "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/check_negative.py"
        --exe "$<TARGET_FILE:interpreter-aarch64-abi-bad_saved>" --runner
        ${CMAKE_CROSSCOMPILING_EMULATOR})
set_tests_properties(interpreter-aarch64-saved-negative PROPERTIES PASS_REGULAR_EXPRESSION
                                                                   "AARCH64_BAD_SAVED_REJECTED")
add_test(
    NAME interpreter-aarch64-image-contract
    COMMAND
        "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tools/arm64/verify/check_abi.py"
        --source "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}" --image
        "$<TARGET_FILE:interpreter-aarch64-abi-normal>" --archive "$<TARGET_FILE:qjs>" --ar
        "${CMAKE_AR}" --object "$<TARGET_OBJECTS:qjs-aarch64-call-abi>" --readelf
        "${CMAKE_READELF}")
add_test(NAME interpreter-aarch64-elf-policy
         COMMAND "${Python3_EXECUTABLE}" -B
                 "${CMAKE_CURRENT_SOURCE_DIR}/tests/arm64/test_elf_machine_arm64.py")

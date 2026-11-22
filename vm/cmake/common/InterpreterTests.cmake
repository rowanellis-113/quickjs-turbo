# Keep the upstream test layout and run semantic checks for both C and native
# backends. Native-only executables link against the actual qjs archive.
enable_testing()
if(QJS_BACKPORT_CONTEXT_OOM)
    add_executable(interpreter-test-promise_oom tests/common/native_promise_oom.c)
    target_compile_features(interpreter-test-promise_oom PRIVATE c_std_11)
    target_link_libraries(interpreter-test-promise_oom PRIVATE qjs)
    add_test(NAME interpreter-promise-oom COMMAND interpreter-test-promise_oom)
    set_tests_properties(interpreter-promise-oom PROPERTIES PASS_REGULAR_EXPRESSION
                                                            "PROMISE_OOM_OK trials=[0-9]+ live=0")
endif()
add_executable(interpreter-env-compat-test tests/common/native_env_compat.c)
target_include_directories(interpreter-env-compat-test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_compile_features(interpreter-env-compat-test PRIVATE c_std_11)
add_test(NAME interpreter-env-compat COMMAND interpreter-env-compat-test)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    add_test(NAME interpreter-target-runner
             COMMAND "${Python3_EXECUTABLE}" -B
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_target_runner.py")
endif()
add_executable(interpreter-test-wire_interop tests/common/wire_interop.c)
target_link_libraries(interpreter-test-wire_interop PRIVATE qjs)
set(qjs_wire_interop_file "${CMAKE_CURRENT_BINARY_DIR}/wire-interop-local.bin")
add_test(NAME interpreter-wire-interop-write COMMAND interpreter-test-wire_interop write
                                                     "${qjs_wire_interop_file}")
set_tests_properties(
    interpreter-wire-interop-write PROPERTIES FIXTURES_SETUP qjs-wire-local PASS_REGULAR_EXPRESSION
                                              "WIRE_INTEROP_OK write")
add_test(NAME interpreter-wire-interop-read COMMAND interpreter-test-wire_interop read
                                                    "${qjs_wire_interop_file}")
set_tests_properties(
    interpreter-wire-interop-read PROPERTIES FIXTURES_REQUIRED qjs-wire-local
                                             PASS_REGULAR_EXPRESSION "WIRE_INTEROP_OK read")
add_test(
    NAME interpreter-cmake-options-compat
    COMMAND
        "${Python3_EXECUTABLE}" -B
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_option_compat.py" --cmake
        "${CMAKE_COMMAND}")
foreach(
    instance_mode
    default
    off
    off-zero
    step-off
    step-off-zero
    leaf-off
    leaf-off-zero)
    add_test(NAME interpreter-instanceof-${instance_mode}
             COMMAND qjs_exe --std "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_instanceof.js")
endforeach()
set_tests_properties(interpreter-instanceof-off PROPERTIES ENVIRONMENT
                                                           "QJS_DISABLE_FRAME_INSTANCEOF=1")
set_tests_properties(interpreter-instanceof-off-zero PROPERTIES ENVIRONMENT
                                                                "QJS_DISABLE_FRAME_INSTANCEOF=0")
set_tests_properties(interpreter-instanceof-step-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_INSTANCEOF_STEP=1")
set_tests_properties(interpreter-instanceof-step-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_INSTANCEOF_STEP=0")
set_tests_properties(interpreter-instanceof-leaf-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_INSTANCEOF_LEAF=1")
set_tests_properties(interpreter-instanceof-leaf-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_INSTANCEOF_LEAF=0")
# Same Number/reference semantics on all backends; GNU native alone emits
# the new no-C truth continuation. Keep explicit independent fallback runs.
add_executable(interpreter-test-number_truth tests/common/native_number_truth.c)
target_compile_features(interpreter-test-number_truth PRIVATE c_std_11)
target_link_libraries(interpreter-test-number_truth PRIVATE qjs)
foreach(number_mode default off off-zero c clean broad-off)
    foreach(number_fixture number_truth number_truth_all)
        add_test(NAME interpreter-${number_fixture}-${number_mode}
                 COMMAND qjs_exe --std
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_${number_fixture}.js")
    endforeach()
    add_test(NAME interpreter-number-truth-host-${number_mode}
             COMMAND interpreter-test-number_truth)
    set_tests_properties(interpreter-number_truth-${number_mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                            "NUMBER_TRUTH_OK 12962")
    set_tests_properties(interpreter-number_truth_all-${number_mode}
                         PROPERTIES PASS_REGULAR_EXPRESSION "NUMBER_TRUTH_ALL_OK 7200")
    set_tests_properties(
        interpreter-number-truth-host-${number_mode}
        PROPERTIES
            PASS_REGULAR_EXPRESSION
            "NUMBER_TRUTH_HOST_OK born=240 finalized=240 collections=240 reentries=240 interrupts=3"
    )
endforeach()
foreach(number_test interpreter-number_truth interpreter-number_truth_all
                    interpreter-number-truth-host)
    set_tests_properties(${number_test}-off PROPERTIES ENVIRONMENT
                                                       "QJS_DISABLE_FRAME_NUMBER_TRUTH=1")
    set_tests_properties(${number_test}-off-zero PROPERTIES ENVIRONMENT
                                                            "QJS_DISABLE_FRAME_NUMBER_TRUTH=0")
    set_tests_properties(
        ${number_test}-c
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    set_tests_properties(${number_test}-clean PROPERTIES ENVIRONMENT
                                                         "QJS_DISABLE_DEFERRED_FRAME_PUBLISH=1")
    set_tests_properties(${number_test}-broad-off PROPERTIES ENVIRONMENT
                                                             "QJS_DISABLE_FRAME_TRUTHINESS=1")
endforeach()
# Existing bytecode semantics on every backend, plus exact public owner/GC
# regressions. Only GNU native emits insert3; all other modes retain C.
add_executable(interpreter-test-stack_insert tests/common/native_stack_insert.c)
target_compile_features(interpreter-test-stack_insert PRIVATE c_std_11)
target_link_libraries(interpreter-test-stack_insert PRIVATE qjs)
foreach(insert_mode default off off-zero c)
    add_test(NAME interpreter-stack-insert-${insert_mode}
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_stack_insert.js")
    add_test(NAME interpreter-stack-insert-host-${insert_mode}
             COMMAND interpreter-test-stack_insert)
    set_tests_properties(interpreter-stack-insert-${insert_mode} PROPERTIES PASS_REGULAR_EXPRESSION
                                                                            "STACK_INSERT_OK 5185")
    set_tests_properties(
        interpreter-stack-insert-host-${insert_mode}
        PROPERTIES
            PASS_REGULAR_EXPRESSION
            "STACK_INSERT_HOST_OK born=160 finalized=160 collections=386 reentries=386 interrupts=3"
    )
endforeach()
foreach(insert_test interpreter-stack-insert interpreter-stack-insert-host)
    set_tests_properties(${insert_test}-off PROPERTIES ENVIRONMENT
                                                       "QJS_DISABLE_FRAME_STACK_INSERT=1")
    set_tests_properties(${insert_test}-off-zero PROPERTIES ENVIRONMENT
                                                            "QJS_DISABLE_FRAME_STACK_INSERT=0")
    set_tests_properties(
        ${insert_test}-c
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
endforeach()
# Semantic fallbacks run on every backend; only the GNU release worker owns
# these private counters. The host also proves both foreign realm guards.
foreach(apply_mode default off off-zero)
    add_test(NAME interpreter-apply-forward-${apply_mode}
             COMMAND qjs_exe --std --stack-size 2048k
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_apply_forward.js")
    set_tests_properties(
        interpreter-apply-forward-${apply_mode}
        PROPERTIES PASS_REGULAR_EXPRESSION "APPLY_SEMANTICS_OK collections=[1-9][0-9]*")
endforeach()
set_tests_properties(interpreter-apply-forward-off PROPERTIES ENVIRONMENT
                                                              "QJS_DISABLE_FRAME_APPLY_DIRECT=1")
set_tests_properties(interpreter-apply-forward-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_APPLY_DIRECT=0")
foreach(argument_ctor_mode default off off-zero)
    add_test(NAME interpreter-argument-constructor-${argument_ctor_mode}
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_argument_constructor.js")
endforeach()
set_tests_properties(interpreter-argument-constructor-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=1")
set_tests_properties(interpreter-argument-constructor-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR=0")
if(NOT QJS_BACKPORT_NATIVE_MODULES AND QJS_BACKPORT_PORTABLE_REGEXP)
    # Exercise the shared C module used by PORTABLE and the Linux backend.
    add_executable(interpreter-test-wire tests/common/native_wire.c)
    target_compile_features(interpreter-test-wire PRIVATE c_std_11)
    target_link_libraries(interpreter-test-wire PRIVATE qjs)
    add_test(NAME interpreter-portable-wire COMMAND interpreter-test-wire)
    foreach(regexp_case start differential portable_core bug1221)
        add_test(
            NAME interpreter-portable-regexp-${regexp_case}
            COMMAND qjs_exe -m
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_${regexp_case}.js")
    endforeach()
    set_tests_properties(interpreter-portable-regexp-differential
                         PROPERTIES PASS_REGULAR_EXPRESSION "REGEXP_DIFFERENTIAL 251621 9b20c58d")
endif()
find_package(Python3 REQUIRED COMPONENTS Interpreter)
add_test(
    NAME interpreter-source-layout
    COMMAND
        "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/validate_layout.py"
        --source "${CMAKE_CURRENT_SOURCE_DIR}")
add_test(NAME interpreter-c-source-match
         COMMAND "${Python3_EXECUTABLE}" -B -O
                 "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_c_source_match.py")
add_executable(interpreter-test-file_load tests/common/native_file_load.c)
target_compile_features(interpreter-test-file_load PRIVATE c_std_11)
add_qjs_libc_if_needed(interpreter-test-file_load)
target_link_libraries(interpreter-test-file_load PRIVATE qjs)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(interpreter-test-file_load PRIVATE -UNDEBUG)
elseif(WIN32)
    target_compile_options(interpreter-test-file_load PRIVATE /UNDEBUG)
else()
    target_compile_options(interpreter-test-file_load PRIVATE -UNDEBUG)
endif()
foreach(file_mode default legacy compact-off)
    set(file_directory "${CMAKE_CURRENT_BINARY_DIR}/tests/file-load-${file_mode}")
    file(MAKE_DIRECTORY "${file_directory}")
    add_test(NAME interpreter-file-load-${file_mode} COMMAND interpreter-test-file_load
                                                             "${file_directory}")
endforeach()
set_tests_properties(interpreter-file-load-legacy PROPERTIES ENVIRONMENT
                                                             "QJS_DISABLE_FILE_LOAD_GROWTH=1")
set_tests_properties(interpreter-file-load-compact-off PROPERTIES ENVIRONMENT
                                                                  "QJS_DISABLE_FILE_LOAD_COMPACT=1")
if(QJS_ENABLE_INTERP_FRAME OR QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "PORTABLE")
    foreach(construct_mode native disabled zero noic register-c c)
        foreach(construct_fixture continuation boundary)
            add_test(
                NAME interpreter-construct-${construct_fixture}-${construct_mode}
                COMMAND
                    qjs_exe --std
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_construct_${construct_fixture}.js"
            )
        endforeach()
    endforeach()
    foreach(construct_fixture continuation boundary)
        set_tests_properties(interpreter-construct-${construct_fixture}-disabled
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION=1")
        set_tests_properties(interpreter-construct-${construct_fixture}-zero
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION=0")
        set_tests_properties(interpreter-construct-${construct_fixture}-noic
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=1")
        set_tests_properties(interpreter-construct-${construct_fixture}-register-c
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
        set_tests_properties(
            interpreter-construct-${construct_fixture}-c
            PROPERTIES
                ENVIRONMENT
                "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
        )
    endforeach()
    foreach(long_mode native disabled register-c c)
        add_test(NAME interpreter-long-code-${long_mode}
                 COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_long_code.js")
    endforeach()
    set_tests_properties(interpreter-long-code-disabled PROPERTIES ENVIRONMENT
                                                                   "QJS_DISABLE_FRAME_LONG_CODE=1")
    set_tests_properties(interpreter-long-code-register-c
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-long-code-c
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    foreach(
        large_mode
        native
        enabled
        enabled-zero
        enable-disable
        disabled
        zero
        long-off
        c
        bypass-off
        bypass-zero
        regexp-off
        regexp-zero)
        add_test(NAME interpreter-large-code-${large_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_large_code.js")
    endforeach()
    set_tests_properties(interpreter-large-code-enabled PROPERTIES ENVIRONMENT
                                                                   "QJS_ENABLE_FRAME_LARGE_CODE=1")
    set_tests_properties(interpreter-large-code-enabled-zero
                         PROPERTIES ENVIRONMENT "QJS_ENABLE_FRAME_LARGE_CODE=0")
    set_tests_properties(
        interpreter-large-code-enable-disable
        PROPERTIES ENVIRONMENT "QJS_ENABLE_FRAME_LARGE_CODE=1;QJS_DISABLE_FRAME_LARGE_CODE=0")
    set_tests_properties(interpreter-large-code-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LARGE_CODE=1")
    set_tests_properties(interpreter-large-code-zero PROPERTIES ENVIRONMENT
                                                                "QJS_DISABLE_FRAME_LARGE_CODE=0")
    set_tests_properties(interpreter-large-code-long-off PROPERTIES ENVIRONMENT
                                                                    "QJS_DISABLE_FRAME_LONG_CODE=1")
    set_tests_properties(
        interpreter-large-code-c
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    set_tests_properties(interpreter-large-code-bypass-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LARGE_GLOBAL_BYPASS=1")
    set_tests_properties(interpreter-large-code-bypass-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LARGE_GLOBAL_BYPASS=0")
    set_tests_properties(interpreter-large-code-regexp-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LONG_REGEXP=1")
    set_tests_properties(interpreter-large-code-regexp-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_LONG_REGEXP=0")
    foreach(reference_mode native disabled zero c)
        add_test(NAME interpreter-reference-equality-${reference_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_reference_equality.js")
    endforeach()
    set_tests_properties(interpreter-reference-equality-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_REFERENCE_EQUALITY=1")
    set_tests_properties(interpreter-reference-equality-zero
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_REFERENCE_EQUALITY=0")
    set_tests_properties(
        interpreter-reference-equality-c
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    foreach(wide_mode native disabled register-c c)
        add_test(NAME interpreter-wide-stack-${wide_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_wide_stack.js")
    endforeach()
    set_tests_properties(interpreter-wide-stack-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_WIDE_STACK=1")
    set_tests_properties(interpreter-wide-stack-register-c
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
    set_tests_properties(
        interpreter-wide-stack-c
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    foreach(proto_mode native c)
        add_test(NAME interpreter-prototype-chain-${proto_mode}
                 COMMAND qjs_exe --std
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_prototype_chain.js")
    endforeach()
    set_tests_properties(
        interpreter-prototype-chain-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
    if(NOT BUILD_SHARED_LIBS)
        add_executable(interpreter-test-property_store tests/common/native_property_store.c)
        target_link_libraries(interpreter-test-property_store PRIVATE qjs)
        foreach(store_mode native c)
            add_test(NAME interpreter-property-store-${store_mode}
                     COMMAND interpreter-test-property_store)
        endforeach()
        set_tests_properties(
            interpreter-property-store-c
            PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
    endif()
    foreach(array_mode native c disabled)
        add_test(NAME interpreter-array-copy-${array_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_array_splice.js")
    endforeach()
    set_tests_properties(
        interpreter-array-copy-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
    set_tests_properties(interpreter-array-copy-disabled PROPERTIES ENVIRONMENT
                                                                    "QJS_DISABLE_ARRAY_COPY_GROW=1")
endif()

if(QJS_BACKPORT_CONTEXT_OOM)
    foreach(concat_mode native c disabled)
        add_test(NAME interpreter-string-concat-${concat_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_string_concat.js")
    endforeach()
    set_tests_properties(
        interpreter-string-concat-c
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    set_tests_properties(interpreter-string-concat-disabled PROPERTIES ENVIRONMENT
                                                                       "QJS_DISABLE_CONCAT_ROPE=1")
    foreach(string_mode native c)
        add_test(NAME interpreter-rope-equality-${string_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_rope_equality.js")
    endforeach()
    set_tests_properties(
        interpreter-rope-equality-c
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    if(NOT BUILD_SHARED_LIBS)
        add_executable(interpreter-test-string_concat tests/common/native_string_concat.c)
        target_link_libraries(interpreter-test-string_concat PRIVATE qjs)
        if(QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
            target_compile_definitions(interpreter-test-string_concat
                                       PRIVATE FRAME_TEST_STRING_POOL)
            target_include_directories(interpreter-test-string_concat
                                       PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src/common/memory")
            if(QJS_FRAME_STRING_POOL_NATIVE)
                target_compile_definitions(interpreter-test-string_concat
                                           PRIVATE FRAME_TEST_STRING_POOL_NATIVE)
            endif()
        endif()
        foreach(concat_mode native c disabled)
            add_test(NAME interpreter-string-concat-host-${concat_mode}
                     COMMAND interpreter-test-string_concat)
        endforeach()
        set_tests_properties(
            interpreter-string-concat-host-c
            PROPERTIES
                ENVIRONMENT
                "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
        )
        set_tests_properties(interpreter-string-concat-host-disabled
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_CONCAT_ROPE=1")
        add_test(NAME interpreter-string-concat-host-spare-disabled
                 COMMAND interpreter-test-string_concat)
        set_tests_properties(interpreter-string-concat-host-spare-disabled
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_LOCAL_ROPE_SPARE=1")
        add_test(NAME interpreter-string-concat-spare-disabled
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_string_concat.js")
        set_tests_properties(interpreter-string-concat-spare-disabled
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_LOCAL_ROPE_SPARE=1")
        add_executable(interpreter-test-string_equality tests/common/native_string_equality.c)
        target_link_libraries(interpreter-test-string_equality PRIVATE qjs)
        foreach(string_mode native c)
            add_test(NAME interpreter-rope-equality-host-${string_mode}
                     COMMAND interpreter-test-string_equality)
        endforeach()
        set_tests_properties(
            interpreter-rope-equality-host-c
            PROPERTIES
                ENVIRONMENT
                "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
        )
    endif()
    foreach(locale_mode native c disabled)
        add_test(NAME interpreter-locale-compare-${locale_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_locale_compare.js")
    endforeach()
    set_tests_properties(
        interpreter-locale-compare-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
    set_tests_properties(interpreter-locale-compare-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_LOCALE_COMPARE_LATIN1=1")
endif()
if(QJS_ENABLE_INTERP_FRAME OR QJS_BACKPORT_PORTABLE_REGEXP)
    foreach(regexp_split_mode native disabled)
        add_test(NAME interpreter-regexp-split-${regexp_split_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_split.js")
    endforeach()
    set_tests_properties(interpreter-regexp-split-disabled PROPERTIES ENVIRONMENT
                                                                      "QJS_DISABLE_REGEXP_SPLIT=1")
endif()
if(QJS_ENABLE_INTERP_FRAME OR QJS_BACKPORT_PORTABLE_REGEXP)
    foreach(regexp_byte_mode native disabled start-disabled c)
        add_test(NAME interpreter-regexp-byte-${regexp_byte_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_lookahead.js")
    endforeach()
    set_tests_properties(interpreter-regexp-byte-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_LOOKAHEAD=1")
    set_tests_properties(interpreter-regexp-byte-start-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_START_FILTER=1")
    set_tests_properties(
        interpreter-regexp-byte-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
endif()
if(QJS_ENABLE_INTERP_FRAME OR QJS_BACKPORT_PORTABLE_REGEXP)
    foreach(regexp_window_mode native disabled c)
        add_test(NAME interpreter-regexp-window-${regexp_window_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_window.js")
    endforeach()
    set_tests_properties(interpreter-regexp-window-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_WINDOW=1")
    set_tests_properties(
        interpreter-regexp-window-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
endif()
if(QJS_ENABLE_INTERP_FRAME OR QJS_BACKPORT_PORTABLE_REGEXP)
    add_test(NAME interpreter-regexp-exec-result
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_exec.js")
    set_tests_properties(interpreter-regexp-exec-result PROPERTIES PASS_REGULAR_EXPRESSION
                                                                   "REGEXP_EXEC_RESULT")
    add_executable(interpreter-test-regexp_exec tests/common/native_regexp_exec.c)
    target_link_libraries(interpreter-test-regexp_exec PRIVATE qjs)
    target_compile_features(interpreter-test-regexp_exec PRIVATE c_std_11)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(interpreter-test-regexp_exec PRIVATE -UNDEBUG)
    elseif(WIN32)
        target_compile_options(interpreter-test-regexp_exec PRIVATE /UNDEBUG)
    else()
        target_compile_options(interpreter-test-regexp_exec PRIVATE -UNDEBUG)
    endif()
    add_test(NAME interpreter-regexp-exec-ownership COMMAND interpreter-test-regexp_exec)
    foreach(regexp_literal_mode native disabled c)
        add_test(NAME interpreter-regexp-literal-${regexp_literal_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_literal.js")
        set_tests_properties(interpreter-regexp-literal-${regexp_literal_mode}
                             PROPERTIES PASS_REGULAR_EXPRESSION "REGEXP_LITERAL_OK 41061 730191268")
    endforeach()
    set_tests_properties(interpreter-regexp-literal-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_LITERAL=1")
    set_tests_properties(
        interpreter-regexp-literal-c
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
endif()
if((QJS_ENABLE_INTERP_FRAME OR QJS_BACKPORT_PORTABLE_REGEXP) AND NOT BUILD_SHARED_LIBS)
    add_executable(interpreter-test-regexp_literal tests/common/native_regexp_literal.c)
    target_link_libraries(interpreter-test-regexp_literal PRIVATE qjs)
    target_compile_features(interpreter-test-regexp_literal PRIVATE c_std_11)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(interpreter-test-regexp_literal PRIVATE -UNDEBUG)
    elseif(WIN32)
        target_compile_options(interpreter-test-regexp_literal PRIVATE /UNDEBUG)
    else()
        target_compile_options(interpreter-test-regexp_literal PRIVATE -UNDEBUG)
    endif()
    add_test(NAME interpreter-regexp-literal-raw COMMAND interpreter-test-regexp_literal)
    add_executable(interpreter-test-regexp_compile_oom tests/common/native_regexp_compile_oom.c)
    target_link_libraries(interpreter-test-regexp_compile_oom PRIVATE qjs)
    target_compile_features(interpreter-test-regexp_compile_oom PRIVATE c_std_11)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(interpreter-test-regexp_compile_oom PRIVATE -UNDEBUG)
    elseif(WIN32)
        target_compile_options(interpreter-test-regexp_compile_oom PRIVATE /UNDEBUG)
    else()
        target_compile_options(interpreter-test-regexp_compile_oom PRIVATE -UNDEBUG)
    endif()
    add_test(NAME interpreter-regexp-compile-oom COMMAND interpreter-test-regexp_compile_oom)
endif()
if(QJS_ENABLE_INTERP_FRAME OR QJS_BACKPORT_PORTABLE_REGEXP)
    foreach(regexp_empty_mode native disabled)
        add_test(NAME interpreter-regexp-empty-replace-${regexp_empty_mode}
                 COMMAND qjs_exe -m
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_replace_empty.js")
    endforeach()
    set_tests_properties(interpreter-regexp-empty-replace-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_REPLACE_EMPTY=1")
endif()
if(QJS_ENABLE_INTERP_FRAME OR QJS_BACKPORT_PORTABLE_REGEXP)
    add_executable(interpreter-test-regexp_replace_oom tests/common/native_regexp_replace_oom.c)
    target_link_libraries(interpreter-test-regexp_replace_oom PRIVATE qjs)
    target_compile_features(interpreter-test-regexp_replace_oom PRIVATE c_std_11)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(interpreter-test-regexp_replace_oom PRIVATE -UNDEBUG)
    elseif(WIN32)
        target_compile_options(interpreter-test-regexp_replace_oom PRIVATE /UNDEBUG)
    else()
        target_compile_options(interpreter-test-regexp_replace_oom PRIVATE -UNDEBUG)
    endif()
    foreach(regexp_replace_fault_mode native disabled)
        add_test(NAME interpreter-regexp-replace-oom-${regexp_replace_fault_mode}
                 COMMAND interpreter-test-regexp_replace_oom)
    endforeach()
    set_tests_properties(interpreter-regexp-replace-oom-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_REPLACE_EMPTY=1")
endif()
if(QJS_ENABLE_INTERP_FRAME OR QJS_BACKPORT_PORTABLE_REGEXP)
    foreach(regexp_unicode_mode native disabled)
        add_test(
            NAME interpreter-regexp-replace-unicode-${regexp_unicode_mode}
            COMMAND qjs_exe -m
                    "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_regexp_replace_unicode.js")
    endforeach()
    set_tests_properties(interpreter-regexp-replace-unicode-disabled
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_REGEXP_REPLACE_EMPTY=1")
endif()
if(QJS_PROPERTY_IC)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    # Public embedding contracts also run against shared/PORTABLE libraries.
    add_executable(interpreter-test-property_ic_public tests/common/native_property_ic_public.c)
    target_compile_features(interpreter-test-property_ic_public PRIVATE c_std_11)
    target_link_libraries(interpreter-test-property_ic_public PRIVATE qjs)
    foreach(mode default c adaptive-off ic-off)
        add_test(NAME interpreter-property-ic-public-${mode}
                 COMMAND interpreter-test-property_ic_public)
    endforeach()
    set_tests_properties(
        interpreter-property-ic-public-c
        PROPERTIES
            ENVIRONMENT
            "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1"
    )
    set_tests_properties(interpreter-property-ic-public-adaptive-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_IC_ADAPTIVE_WAYS=1")
    set_tests_properties(interpreter-property-ic-public-ic-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=1")
    add_test(NAME interpreter-property-generator
             COMMAND "${Python3_EXECUTABLE}" -B
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_property_ic_generator.py")
    add_test(NAME interpreter-property-ic
             COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_property_ic.js")
    add_test(NAME interpreter-property-ic-c
             COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_property_ic.js")
    set_tests_properties(
        interpreter-property-ic-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
    add_test(NAME interpreter-property-ic-disabled
             COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_property_ic.js")
    set_tests_properties(interpreter-property-ic-disabled PROPERTIES ENVIRONMENT
                                                                     "QJS_DISABLE_PROPERTY_IC=1")
    if(NOT BUILD_SHARED_LIBS)
        add_executable(interpreter-test-property_ic tests/common/native_property_ic.c)
        target_link_libraries(interpreter-test-property_ic PRIVATE qjs)
        add_test(NAME interpreter-property-ic-host COMMAND interpreter-test-property_ic)
        add_test(NAME interpreter-property-ic-host-c COMMAND interpreter-test-property_ic)
        set_tests_properties(
            interpreter-property-ic-host-c
            PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
        add_test(NAME interpreter-property-ic-host-disabled COMMAND interpreter-test-property_ic)
        set_tests_properties(interpreter-property-ic-host-disabled
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=1")
        add_test(NAME interpreter-property-ic-host-retain COMMAND interpreter-test-property_ic)
        set_tests_properties(interpreter-property-ic-host-retain
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC_WEAK_PROTO=1")
        add_executable(interpreter-test-property_ic_adaptive
                       tests/common/native_property_ic_adaptive.c)
        target_link_libraries(interpreter-test-property_ic_adaptive PRIVATE qjs)
        add_test(NAME interpreter-property-ic-adaptive
                 COMMAND interpreter-test-property_ic_adaptive)
        add_test(NAME interpreter-property-ic-adaptive-c
                 COMMAND interpreter-test-property_ic_adaptive)
        set_tests_properties(interpreter-property-ic-adaptive-c
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
        add_test(NAME interpreter-property-ic-adaptive-off
                 COMMAND interpreter-test-property_ic_adaptive)
        set_tests_properties(interpreter-property-ic-adaptive-off
                             PROPERTIES ENVIRONMENT "QJS_DISABLE_IC_ADAPTIVE_WAYS=1")
    endif()
endif()
if(QJS_BACKPORT_MAP_POINTER_HASH)
    add_test(NAME interpreter-map-pointer-hash
             COMMAND qjs_exe -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_map_pointer_hash.js")
    add_test(NAME interpreter-map-pointer-hash-c
             COMMAND qjs_exe -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_map_pointer_hash.js")
    set_tests_properties(
        interpreter-map-pointer-hash-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
endif()
if(QJS_BACKPORT_VALUE64_INIT OR QJS_BACKPORT_MIXED_NUMBERS)
    add_test(NAME interpreter-bellard-numbers
             COMMAND qjs_exe -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_bellard_numbers.js")
    add_test(NAME interpreter-bellard-numbers-c
             COMMAND qjs_exe -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_bellard_numbers.js")
    set_tests_properties(
        interpreter-bellard-numbers-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
    add_executable(interpreter-test-value-payload tests/common/native_value_payload.c)
    target_link_libraries(interpreter-test-value-payload PRIVATE qjs)
    add_test(NAME interpreter-value-payload-host-abi COMMAND interpreter-test-value-payload)
    add_test(NAME interpreter-value-payload-host-abi-c COMMAND interpreter-test-value-payload)
    set_tests_properties(
        interpreter-value-payload-host-abi-c
        PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1")
endif()
if(QJS_FRAME_EXPERIMENTAL_ALLOCATOR AND NOT BUILD_SHARED_LIBS)
    add_executable(interpreter-test-pool tests/common/test_pool.c)
    target_link_libraries(interpreter-test-pool PRIVATE qjs)
    add_test(NAME interpreter-pool-contract COMMAND interpreter-test-pool)
endif()
if(QJS_ENABLE_INTERP_FRAME AND QJS_FRAME_EXPERIMENTAL_COMPARE)
    add_test(NAME interpreter-number-compare
             COMMAND qjs_exe -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_number_compare.js")
endif()
if(QJS_BACKPORT_COMPUTED_ASSIGN)
    add_test(NAME interpreter-computed-assign
             COMMAND qjs_exe -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_computed_assign.js")
endif()
add_test(NAME upstream-language COMMAND run-test262 -c tests.conf -f tests/test_language.js)
add_test(NAME upstream-builtins COMMAND run-test262 -c tests.conf -f tests/test_builtin.js)
set_tests_properties(upstream-language upstream-builtins PROPERTIES WORKING_DIRECTORY
                                                                    "${QJS_UPSTREAM_DIR}")
add_test(NAME upstream-api COMMAND api-test)
add_test(NAME interpreter-semantics
         COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_semantics.js")
add_test(NAME interpreter-character-set-leaf
         COMMAND qjs_exe --std -m
                 "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_character_set_leaf.js")
add_test(NAME interpreter-character-set-leaf-off
         COMMAND qjs_exe --std -m
                 "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_character_set_leaf.js")
set_tests_properties(interpreter-character-set-leaf-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_FRAME_CHARACTER_SET_LEAF=0")
add_test(NAME interpreter-minimum-calls
         COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_min_call_state.js")

# Closure storage remains observable through GC, OOM and public embedding.
add_executable(interpreter-test-coroutine_segments tests/common/native_coroutine_segments.c)
target_compile_features(interpreter-test-coroutine_segments PRIVATE c_std_11)
target_link_libraries(interpreter-test-coroutine_segments PRIVATE qjs)
foreach(
    coroutine_mode
    default
    off
    off-zero
    clone-only
    c
    register-c
    noic
    closure-off)
    add_test(
        NAME interpreter-coroutine-segments-${coroutine_mode}
        COMMAND qjs_exe --std -m
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_coroutine_native_segments.js")
    add_test(NAME interpreter-coroutine-segments-host-${coroutine_mode}
             COMMAND interpreter-test-coroutine_segments)
endforeach()
set_tests_properties(interpreter-coroutine-segments-off interpreter-coroutine-segments-host-off
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_CVM_NATIVE_SEGMENTS=1")
set_tests_properties(
    interpreter-coroutine-segments-off-zero interpreter-coroutine-segments-host-off-zero
    PROPERTIES ENVIRONMENT "QJS_DISABLE_CVM_NATIVE_SEGMENTS=0")
set_tests_properties(
    interpreter-coroutine-segments-clone-only interpreter-coroutine-segments-host-clone-only
    PROPERTIES ENVIRONMENT "QJS_DISABLE_CVM_NATIVE_SEGMENT_OPS=1")
set_tests_properties(
    interpreter-coroutine-segments-c interpreter-coroutine-segments-host-c
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(
    interpreter-coroutine-segments-register-c interpreter-coroutine-segments-host-register-c
    PROPERTIES ENVIRONMENT "QJS_DISABLE_REGISTER_INTERP=1")
set_tests_properties(interpreter-coroutine-segments-noic interpreter-coroutine-segments-host-noic
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_PROPERTY_IC=1")
set_tests_properties(
    interpreter-coroutine-segments-closure-off interpreter-coroutine-segments-host-closure-off
    PROPERTIES ENVIRONMENT "QJS_DISABLE_CLOSURE_INLINE_REFS=1;QJS_DISABLE_CLOSURE_SHAPE_TEMPLATE=1")
foreach(internal_function_mode native disabled disabled-zero c)
    add_test(
        NAME interpreter-internal-function-template-${internal_function_mode}
        COMMAND qjs_exe --std -m
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_internal_function_template.js")
endforeach()
set_tests_properties(interpreter-internal-function-template-disabled
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERNAL_FUNCTION_TEMPLATE=1")
set_tests_properties(interpreter-internal-function-template-disabled-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_INTERNAL_FUNCTION_TEMPLATE=0")
set_tests_properties(
    interpreter-internal-function-template-c
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1")
foreach(closure_mode native inline-disabled template-disabled c)
    add_test(NAME interpreter-closure-storage-${closure_mode}
             COMMAND qjs_exe --std -m
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_closure_template.js")
endforeach()
set_tests_properties(interpreter-closure-storage-inline-disabled
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_CLOSURE_INLINE_REFS=1")
set_tests_properties(interpreter-closure-storage-template-disabled
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_CLOSURE_SHAPE_TEMPLATE=1")
set_tests_properties(
    interpreter-closure-storage-c
    PROPERTIES
        ENVIRONMENT
        "QJS_DISABLE_INTERP_FRAME=1;QJS_DISABLE_INTERNAL_INTERP=1;QJS_DISABLE_REGISTER_INTERP=1")

# The language fixture also covers the unchanged portable fallback.
add_test(NAME array-default-string-sort
         COMMAND qjs_exe --std
                 "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_default_string_sort.js")
add_test(NAME array-default-string-sort-off-zero
         COMMAND qjs_exe --std
                 "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_default_string_sort.js")
set_tests_properties(array-default-string-sort-off-zero
                     PROPERTIES ENVIRONMENT "QJS_DISABLE_DEFAULT_STRING_RADIX=0")

# Promise representation and ownership semantics also exercise PORTABLE.
add_executable(interpreter-test-async_capability tests/common/native_async_capability.c)
target_compile_features(interpreter-test-async_capability PRIVATE c_std_11)
target_link_libraries(interpreter-test-async_capability PRIVATE qjs)
foreach(async_kind generator function)
    foreach(async_mode on off clone)
        add_test(
            NAME async-${async_kind}-capability-${async_mode}
            COMMAND
                qjs_exe --std
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_async_${async_kind}_capability.js"
        )
        set_tests_properties(
            async-${async_kind}-capability-${async_mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "\"passed\":true" FAIL_REGULAR_EXPRESSION "FAIL")
    endforeach()
    set_tests_properties(async-${async_kind}-capability-off
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_GENERATOR_CAPABILITY=0")
    set_tests_properties(async-${async_kind}-capability-clone
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_GENERATOR_CAPABILITY_FAST=0")
endforeach()
foreach(async_kind generator ordinary)
    add_test(NAME async-${async_kind}-ownership COMMAND interpreter-test-async_capability
                                                        ${async_kind})
    add_test(NAME async-${async_kind}-oom-sweep COMMAND interpreter-test-async_capability
                                                        ${async_kind} sweep)
endforeach()

# Common compiler semantics and public owners; meaningful on native and portable backends.
if(QJS_BACKPORT_CONTEXT_OOM)
    add_executable(interpreter-test-compiler-plan tests/common/native_compiler_plan.c)
    target_compile_features(interpreter-test-compiler-plan PRIVATE c_std_11)
    target_link_libraries(interpreter-test-compiler-plan PRIVATE qjs)
    add_test(NAME interpreter-compiler-plan-bytecode COMMAND interpreter-test-compiler-plan
                                                             --bytecode)
    set_tests_properties(interpreter-compiler-plan-bytecode PROPERTIES PASS_REGULAR_EXPRESSION
                                                                       "COMPILER_PLAN_BYTECODE_OK")
    foreach(compiler_mode enabled checks-only entry-only disabled)
        add_test(NAME interpreter-compiler-plan-${compiler_mode}
                 COMMAND qjs_exe --std
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_vm_compiler_plan.js")
        add_test(NAME interpreter-compiler-owner-${compiler_mode}
                 COMMAND interpreter-test-compiler-plan)
        set_tests_properties(
            interpreter-compiler-plan-${compiler_mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "ENTRY_INIT_SEMANTICS_OK" FAIL_REGULAR_EXPRESSION
                       "Error:|Assertion failed")
        set_tests_properties(
            interpreter-compiler-owner-${compiler_mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "ENTRY_INIT_OWNERSHIP_OK born=10 finalized=10")
        if(compiler_mode STREQUAL "checks-only")
            set(compiler_environment "QJS_DISABLE_TDZ_INIT=0")
        elseif(compiler_mode STREQUAL "entry-only")
            set(compiler_environment "QJS_DISABLE_TDZ_PLAN=0")
        elseif(compiler_mode STREQUAL "disabled")
            set(compiler_environment "QJS_DISABLE_TDZ_PLAN=0;QJS_DISABLE_TDZ_INIT=0")
        else()
            set(compiler_environment "")
        endif()
        set_tests_properties(
            interpreter-compiler-plan-${compiler_mode} interpreter-compiler-owner-${compiler_mode}
            PROPERTIES ENVIRONMENT "${compiler_environment}")
    endforeach()
endif()

# Public semantics and interrupt ownership for resolved Symbol conditions.
if(QJS_BACKPORT_CONTEXT_OOM)
    add_executable(interpreter-test-symbol-conditions tests/common/native_symbol_conditions.c)
    target_compile_features(interpreter-test-symbol-conditions PRIVATE c_std_11)
    target_link_libraries(interpreter-test-symbol-conditions PRIVATE qjs)
    foreach(symbol_mode enabled disabled bindings-off large-off)
        add_test(NAME interpreter-symbol-conditions-${symbol_mode}
                 COMMAND qjs_exe --std
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_symbol_conditions.js")
        set_tests_properties(
            interpreter-symbol-conditions-${symbol_mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "SYMBOL_CONDITIONS_OK" FAIL_REGULAR_EXPRESSION
                       "Error:|Assertion failed")
        if(symbol_mode STREQUAL "disabled")
            set(symbol_environment "QJS_DISABLE_SYMBOL_CASE=0")
        elseif(symbol_mode STREQUAL "bindings-off")
            set(symbol_environment "QJS_DISABLE_FRAME_BINDING_CELL=0")
        elseif(symbol_mode STREQUAL "large-off")
            set(symbol_environment "QJS_DISABLE_FRAME_LARGE_CODE=0")
        else()
            set(symbol_environment "")
        endif()
        set_tests_properties(interpreter-symbol-conditions-${symbol_mode}
                             PROPERTIES ENVIRONMENT "${symbol_environment}")
    endforeach()
    if(Python3_EXECUTABLE)
        add_test(
            NAME interpreter-symbol-conditions-interrupt
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_symbol_conditions_interrupt.py"
                --exe "$<TARGET_FILE:interpreter-test-symbol-conditions>" --runner
                ${CMAKE_CROSSCOMPILING_EMULATOR})
        set_tests_properties(
            interpreter-symbol-conditions-interrupt
            PROPERTIES PASS_REGULAR_EXPRESSION "SYMBOL_CONDITIONS_PUBLIC_OK records=16")
    endif()
endif()

if(QJS_HYBRID_GC
   AND QJS_BACKPORT_CONTEXT_OOM
   AND NOT QJS_BACKPORT_NATIVE_MODULES)
    foreach(hybrid_mode default off no-partial no-fast-rc)
        add_test(NAME interpreter-hybrid-gc-${hybrid_mode}
                 COMMAND qjs_exe --std
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_hybrid_gc_ab.js")
        set_tests_properties(
            interpreter-hybrid-gc-${hybrid_mode}
            PROPERTIES PASS_REGULAR_EXPRESSION "HYBRID_GC_AB_TORTURE_OK" FAIL_REGULAR_EXPRESSION
                       "Error:|Assertion failed")
    endforeach()
    set_tests_properties(interpreter-hybrid-gc-off PROPERTIES ENVIRONMENT "QJS_DISABLE_HYBRID_GC=1")
    set_tests_properties(interpreter-hybrid-gc-no-partial PROPERTIES ENVIRONMENT
                                                                     "QJS_DISABLE_PARTIAL_CYCLE=1")
    set_tests_properties(interpreter-hybrid-gc-no-fast-rc PROPERTIES ENVIRONMENT
                                                                     "QJS_DISABLE_FAST_RC=1")
    if(QJS_FRAME_EXPERIMENTAL_ALLOCATOR)
        add_test(NAME interpreter-hybrid-gc-pool512
                 COMMAND qjs_exe --std
                         "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_hybrid_gc_ab.js")
        set_tests_properties(
            interpreter-hybrid-gc-pool512
            PROPERTIES ENVIRONMENT "QJS_EXPERIMENT_ALLOCATOR=512" PASS_REGULAR_EXPRESSION
                       "HYBRID_GC_AB_TORTURE_OK" FAIL_REGULAR_EXPRESSION "Error:|Assertion failed")
    endif()
endif()

if(QJS_BACKPORT_CONTEXT_OOM)
    add_test(NAME interpreter-keyed-async-fastpaths
             COMMAND qjs_exe --std
                     "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_keyed_async_fastpaths.js")
    set_tests_properties(
        interpreter-keyed-async-fastpaths
        PROPERTIES PASS_REGULAR_EXPRESSION "KEYED_ASYNC_FASTPATHS_OK" FAIL_REGULAR_EXPRESSION
                   "KEYED_ASYNC_FASTPATHS_FAIL|Error:|Assertion failed")
endif()

add_executable(interpreter-test-turbo_api tests/common/test_turbo_api.c)
target_compile_features(interpreter-test-turbo_api PRIVATE c_std_11)
target_link_libraries(interpreter-test-turbo_api PRIVATE quickjs-turbo::qjs)
add_test(NAME interpreter-turbo-api COMMAND interpreter-test-turbo_api)
set_tests_properties(interpreter-turbo-api PROPERTIES PASS_REGULAR_EXPRESSION "TURBO_API_PASS")
if(QJS_PROPERTY_IC)
    add_test(NAME interpreter-property-ic-pic-only
             COMMAND qjs_exe -m "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_property_ic.js")
    set_tests_properties(interpreter-property-ic-pic-only
                         PROPERTIES ENVIRONMENT "QJS_DISABLE_OWN_BYTECODE_TAIL=1")
endif()

add_test(NAME interpreter-arch-boundaries
         COMMAND "${Python3_EXECUTABLE}" -B
                 "${CMAKE_CURRENT_SOURCE_DIR}/tests/common/test_arch_boundaries.py")

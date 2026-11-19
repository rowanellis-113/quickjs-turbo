# Measure with the selected compiler and flags before admitting native code.
# A source hash alone cannot detect e.g. MinGW -mno-ms-bitfields or /Zp changes.
function(qjs_frame_verify_abi frame_source)
    set(frame_abi_dir "${CMAKE_CURRENT_BINARY_DIR}/generated")
    file(MAKE_DIRECTORY "${frame_abi_dir}")
    execute_process(
        COMMAND "${Python3_EXECUTABLE}" -B "${frame_source}/tools/common/abi/generate_layout.py"
                --source "${frame_source}" --output "${frame_abi_dir}/interpreter-layout-probe.c"
        RESULT_VARIABLE frame_abi_generate
        OUTPUT_VARIABLE frame_abi_generate_output
        ERROR_VARIABLE frame_abi_generate_error)
    if(NOT frame_abi_generate EQUAL 0)
        message(
            FATAL_ERROR
                "Cannot generate the selected-source ABI probe: ${frame_abi_generate_output}${frame_abi_generate_error}"
        )
    endif()
    unset(frame_abi_run CACHE)
    unset(frame_abi_compile CACHE)
    # These probes are for the admitted Windows x64 host compiler. Unsupported
    # targets/cross-compilers are rejected by platform policy before this step.
    set(CMAKE_TRY_COMPILE_CONFIGURATION Release)
    set(frame_abi_cmake_flags "-DINCLUDE_DIRECTORIES:STRING=${QJS_UPSTREAM_DIR}\;${frame_source}"
                              "-DCMAKE_C_STANDARD:STRING=11")
    if(DEFINED CMAKE_MSVC_RUNTIME_LIBRARY)
        list(APPEND frame_abi_cmake_flags
             "-DCMAKE_MSVC_RUNTIME_LIBRARY:STRING=${CMAKE_MSVC_RUNTIME_LIBRARY}")
    endif()
    try_run(
        frame_abi_run frame_abi_compile "${frame_abi_dir}/probe-build"
        "${frame_abi_dir}/interpreter-layout-probe.c"
        CMAKE_FLAGS ${frame_abi_cmake_flags}
        COMPILE_OUTPUT_VARIABLE frame_abi_compile_output
        RUN_OUTPUT_VARIABLE frame_abi_actual)
    if(NOT frame_abi_compile OR NOT frame_abi_run EQUAL 0)
        message(
            FATAL_ERROR
                "The selected compiler cannot measure the native ABI: ${frame_abi_compile_output}\n${frame_abi_actual}"
        )
    endif()
    file(WRITE "${frame_abi_dir}/interpreter-abi-measured.json" "${frame_abi_actual}")
    execute_process(
        COMMAND
            "${Python3_EXECUTABLE}" -B "${frame_source}/tools/x86/common/abi/abi_layout.py" --source
            "${frame_source}" --actual "${frame_abi_dir}/interpreter-abi-measured.json" --output
            "${frame_abi_dir}"
        RESULT_VARIABLE frame_abi_verify
        OUTPUT_VARIABLE frame_abi_verify_output
        ERROR_VARIABLE frame_abi_verify_error)
    if(NOT frame_abi_verify EQUAL 0)
        message(
            FATAL_ERROR
                "Native ABI differs from the measured source contract. Review compiler layout flags or port the backend.\n${frame_abi_verify_output}${frame_abi_verify_error}"
        )
    endif()
    message(STATUS "QuickJS frame ABI: compiler measurements match the selected-source contract")
endfunction()

if(QJS_FRAME_BACKEND_EFFECTIVE STREQUAL "MACOS_X86_64")
    if(TARGET qjs_exe AND NOT QJS_USE_PREGEN_ASM)
        add_custom_command(
            TARGET qjs_exe
            POST_BUILD
            COMMAND
                "${Python3_EXECUTABLE}" -B
                "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/macos/record-native.py" --source
                "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}" --binary
                "$<TARGET_FILE:qjs_exe>" --archive "$<TARGET_FILE:qjs>"
            VERBATIM)
    endif()
    if(QJS_ENABLE_INSTALL)
        set(qjs_macos_install_files "${CMAKE_CURRENT_BINARY_DIR}/interpreter-backend.json")
        if(TARGET qjs_exe AND NOT QJS_USE_PREGEN_ASM)
            list(APPEND qjs_macos_install_files "${CMAKE_CURRENT_BINARY_DIR}/BUILD.json"
                 "${CMAKE_CURRENT_BINARY_DIR}/native-macho.txt")
        endif()
        install(FILES ${qjs_macos_install_files} DESTINATION "${CMAKE_INSTALL_DOCDIR}")
    endif()
endif()

# Native compiler-only contributions use the existing late code/data family.
set(compiler_plan_analysis "${QJS_FRAME_GENERATED_DIR}/quickjs-compiler-plan-analysis.obj")
set(compiler_plan_projection "${QJS_FRAME_GENERATED_DIR}/quickjs-compiler-plan-projection.obj")
add_custom_command(
    OUTPUT "${compiler_plan_analysis}" "${compiler_plan_projection}"
    COMMAND
        "${Python3_EXECUTABLE}" -B
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/x86/win64/codegen/compiler-plan.py" --source
        "${CMAKE_CURRENT_SOURCE_DIR}" --build "${CMAKE_CURRENT_BINARY_DIR}"
    DEPENDS "${frame_private_header}"
            tools/x86/win64/codegen/compiler-plan.py
            tools/x86/win64/codegen/atod.py
            tools/x86/win64/coff/object-adapter.py
            src/common/bytecode/compiler-plan.c
            src/common/bytecode/compiler-plan-view.h
            src/common/bytecode/compiler-plan-shim.inc
    VERBATIM)
set_source_files_properties("${compiler_plan_analysis}" "${compiler_plan_projection}"
                            PROPERTIES GENERATED TRUE EXTERNAL_OBJECT TRUE)
target_sources(qjs PRIVATE "${compiler_plan_analysis}" "${compiler_plan_projection}")

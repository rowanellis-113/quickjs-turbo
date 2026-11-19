# Linux/glibc AArch64 cross build. Backend selection is explicit: the
# product AArch64 wrapper requests LINUX_AARCH64;PORTABLE remains available.
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

set(QJS_AARCH64_TOOLCHAIN_PREFIX
    "aarch64-linux-gnu"
    CACHE STRING "GNU cross tool prefix, optionally including an absolute directory")
set(CMAKE_C_COMPILER
    "${QJS_AARCH64_TOOLCHAIN_PREFIX}-gcc"
    CACHE FILEPATH "Target C compiler")
set(CMAKE_AR
    "${QJS_AARCH64_TOOLCHAIN_PREFIX}-ar"
    CACHE FILEPATH "Target archiver")
set(CMAKE_RANLIB
    "${QJS_AARCH64_TOOLCHAIN_PREFIX}-ranlib"
    CACHE FILEPATH "Target ranlib")
set(CMAKE_C_FLAGS_INIT "-march=armv8-a")

# Debian/Ubuntu GCC supplies its own sysroot/specs. Do not overwrite
# CMAKE_SYSROOT with this library search root (GCC reports '/' as its sysroot).
set(QJS_AARCH64_TARGET_ROOT
    "/usr/aarch64-linux-gnu"
    CACHE PATH "Target library search root")
list(APPEND CMAKE_FIND_ROOT_PATH "${QJS_AARCH64_TARGET_ROOT}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

# QEMU is optional for compilation. A caller may instead provide an explicit
# CMAKE_CROSSCOMPILING_EMULATOR list, or test the installed SDK on real ARM.
set(QJS_AARCH64_QEMU_CPU
    "cortex-a53"
    CACHE STRING "QEMU target CPU for functional tests")
set(QJS_AARCH64_QEMU_LD_PREFIX
    "${QJS_AARCH64_TARGET_ROOT}"
    CACHE PATH "QEMU guest loader/library prefix")
if(NOT DEFINED CMAKE_CROSSCOMPILING_EMULATOR)
    find_program(
        QJS_AARCH64_QEMU
        NAMES qemu-aarch64
        NO_CMAKE_FIND_ROOT_PATH)
    if(QJS_AARCH64_QEMU)
        set(CMAKE_CROSSCOMPILING_EMULATOR
            "${QJS_AARCH64_QEMU};-cpu;${QJS_AARCH64_QEMU_CPU};-L;${QJS_AARCH64_QEMU_LD_PREFIX}"
            CACHE STRING "Runner for target executables")
    endif()
endif()
list(
    APPEND
    CMAKE_TRY_COMPILE_PLATFORM_VARIABLES
    QJS_AARCH64_TOOLCHAIN_PREFIX
    QJS_AARCH64_TARGET_ROOT
    QJS_AARCH64_QEMU
    QJS_AARCH64_QEMU_CPU
    QJS_AARCH64_QEMU_LD_PREFIX)

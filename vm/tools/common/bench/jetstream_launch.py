import ctypes
import os
from pathlib import Path
import time

kernel = ctypes.windll.kernel32
kernel.GetCurrentProcess.restype = ctypes.c_void_p
kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]


def observe_process(pid, image):
    from ctypes import wintypes as W

    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    psapi.EnumProcessModulesEx.argtypes = [
        W.HANDLE,
        ctypes.POINTER(W.HMODULE),
        W.DWORD,
        ctypes.POINTER(W.DWORD),
        W.DWORD,
    ]
    psapi.GetModuleFileNameExW.argtypes = [W.HANDLE, W.HMODULE, W.LPWSTR, W.DWORD]
    kernel.GetProcessAffinityMask.argtypes = [
        W.HANDLE,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    handle = kernel.OpenProcess(0x0410, False, pid)
    if not handle:
        return dict(status="process-unavailable", error=ctypes.get_last_error())
    try:
        process_mask = ctypes.c_size_t()
        system_mask = ctypes.c_size_t()
        assert kernel.GetProcessAffinityMask(
            handle, ctypes.byref(process_mask), ctypes.byref(system_mask)
        )
        assert process_mask.value == 4, (pid, process_mask.value)
        modules = (W.HMODULE * 1024)()
        needed = W.DWORD()
        required = {Path(image["path"]).name.lower(), "kernelbase.dll"}
        if image["engine"] == "jsc":
            required.add("libjavascriptcore.dll")
        # CRT/runtime dependencies vary between MSVCRT and UCRT toolchains.
        required.update(name.lower() for name in image.get("required_modules", []))
        rows = []
        names = set()
        for attempt in range(100):
            ok = psapi.EnumProcessModulesEx(
                handle, modules, ctypes.sizeof(modules), ctypes.byref(needed), 3
            )
            if ok:
                assert needed.value <= ctypes.sizeof(modules)
                rows = []
                for module in list(modules)[: needed.value // ctypes.sizeof(W.HMODULE)]:
                    name = ctypes.create_unicode_buffer(32768)
                    if psapi.GetModuleFileNameExW(handle, module, name, len(name)):
                        rows.append(
                            dict(
                                path=name.value,
                                natural_base=hex(module),
                                rva_origin="module base; no sampled instruction RVAs in this benchmark",
                            )
                        )
                names = {Path(m["path"]).name.lower() for m in rows}
                if required <= names:
                    break
            time.sleep(0.005)
        assert required <= names, (pid, image["name"], "incomplete loader observation", rows)
        return dict(status="observed", affinity_mask=process_mask.value, modules=rows)
    finally:
        kernel.CloseHandle(handle)


def environment(image):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("QJS_", "JSC_", "BENCH_", "NODE_OPTIONS", "NODE_V8_COVERAGE"))
    }
    env.update(image.get("environment", {}))
    runtime_paths = image.get("runtime_paths", [])
    for directory in runtime_paths:
        if not Path(directory).is_absolute() or not Path(directory).is_dir():
            raise ValueError(
                "runtime_paths must name existing absolute directories: " + str(directory)
            )
    env["PATH"] = os.pathsep.join(
        [str(Path(image["path"]).resolve().parent), *runtime_paths, env.get("PATH", "")]
    )
    return env

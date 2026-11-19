"""x86-64 Linux JSON worker family adapter (SSE2 + SysV)."""

import re
from common.elf.json_workers import generate as shared_generate

VEC_REV = {
    "qjs_vec_setzero_si128": "_mm_setzero_si128",
    "qjs_vec_set1_epi8": "_mm_set1_epi8",
    "qjs_vec_set1_epi16": "_mm_set1_epi16",
    "qjs_vec_loadu_si128": "_mm_loadu_si128",
    "qjs_vec_storeu_si128": "_mm_storeu_si128",
    "qjs_vec_or_si128": "_mm_or_si128",
    "qjs_vec_and_si128": "_mm_and_si128",
    "qjs_vec_cmpeq_epi8": "_mm_cmpeq_epi8",
    "qjs_vec_cmpeq_epi16": "_mm_cmpeq_epi16",
    "qjs_vec_subs_epu8": "_mm_subs_epu8",
    "qjs_vec_subs_epu16": "_mm_subs_epu16",
    "qjs_vec_sub_epi16": "_mm_sub_epi16",
    "qjs_vec_unpacklo_epi8": "_mm_unpacklo_epi8",
    "qjs_vec_unpackhi_epi8": "_mm_unpackhi_epi8",
    "qjs_vec_movemask_epi8": "_mm_movemask_epi8",
}


def _adapt(source, output, text, adapter):
    text = text.replace('#include "qjs-json-simd.h"', "#include <emmintrin.h>")
    text = text.replace("/* @QJS_MSC_INTRIN@ */", "#include <intrin.h>")
    text = re.sub(r"\bqjs_vec128_t\b", "__m128i", text)
    text = re.sub(r"\bqjs_vec_\w+\b", lambda m: VEC_REV[m[0]], text)
    text = re.sub(
        r"QJS_CONTROL_SLOT_ADDR\(p,\s*(\w+)\);",
        lambda m: f'__asm__("leaq {m[1]}(%%rip),%0" : "=r"(p));',
        text,
    )
    text = re.sub(
        r"QJS_JSON_STACK_CHECK\(([^,]+),\s*([^\)]+)\);",
        lambda m: (
            "#if defined(__GNUC__) && defined(_WIN32) && defined(__x86_64__) && !defined(_MSC_VER)\n"
            "    uintptr_t sp;\n"
            '    __asm__ volatile("movq %%rsp,%0" : "=r"(sp));\n'
            f"    return unlikely(sp < {m[1].strip()});\n"
            "#else\n"
            f"    return js_check_stack_overflow({m[2].strip()}, 0);\n"
            "#endif"
        ),
        text,
    )
    text = text.replace("QJS_STACK_POINTER(sp);", '__asm__ volatile("movq %%rsp,%0" : "=r"(sp));')
    return text, {}


def generate(source, output, core, adapter, layout):
    return shared_generate(source, output, core, adapter, layout, arch_adapt=_adapt)

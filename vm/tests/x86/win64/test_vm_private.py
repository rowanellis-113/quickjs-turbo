"""Private-source extraction must preserve ownership and active dependencies."""

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from x86.common.paths_x86 import activate_tools, tool_path

activate_tools()
spec = importlib.util.spec_from_file_location("private_source_adapter", tool_path("object-adapter"))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class EmptyCore:
    symbols = {}


SOURCE = """typedef int JSValue;
static inline bool double_is_int32(double value)
{
    return value == 0;
}
static inline int helper(int value) {
    return value + 1;
}
static int owned(int value)
{
    return helper(value);
}
"""


class PrivateSourceContracts(unittest.TestCase):
    def test_inline_opening_brace_is_a_real_dependency(self):
        header, exports, copies = adapter.generate(SOURCE, EmptyCore(), "helper(value)")
        self.assertEqual(exports, [])
        self.assertEqual(copies, ["helper"])
        self.assertIn("return value + 1;", header)

    def test_owned_serializer_functions_are_not_duplicated_or_exported(self):
        header, exports, copies = adapter.generate(
            SOURCE, EmptyCore(), SOURCE[SOURCE.index("static int owned") :], {"owned"}
        )
        self.assertEqual(exports, [])
        self.assertEqual(copies, ["helper"])
        self.assertNotIn("owned(", header)
        self.assertNotIn("qjs_frame_core_owned", header)

    def test_explicit_alias_uses_current_inline_body_when_core_has_no_symbol(self):
        header, exports, copies = adapter.generate(
            SOURCE, EmptyCore(), "qjs_frame_core_helper(value)"
        )
        self.assertEqual(exports, [])
        self.assertEqual(copies, ["helper"])
        self.assertIn("#define qjs_frame_core_helper helper", header)

    def test_disabled_dump_branch_does_not_erase_unknown_feature_branches(self):
        source = """#ifdef ENABLE_DUMPS
dump_only();
#ifdef UNKNOWN
nested_dump();
#endif
#else
release_only();
#if OTHER_FEATURE
first_path();
#else
second_path();
#endif
#endif
after_guard();
"""
        result = adapter.dependency_source(source, {"ENABLE_DUMPS"})
        self.assertNotIn("dump_only", result)
        self.assertNotIn("nested_dump", result)
        for name in ("release_only", "first_path", "second_path", "after_guard"):
            self.assertIn(name, result)
        self.assertEqual(adapter.dependency_source(source, ()), source)

    def test_unreviewed_feature_expressions_and_unbalanced_guards_fail(self):
        for source in (
            "#if defined(ENABLE_DUMPS) && OTHER\ncall();\n#endif\n",
            "#ifdef ENABLE_DUMPS\ncall();\n",
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                adapter.dependency_source(source, {"ENABLE_DUMPS"})


if __name__ == "__main__":
    unittest.main()

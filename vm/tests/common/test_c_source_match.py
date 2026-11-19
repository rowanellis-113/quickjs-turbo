"""Behavior checks for whitespace-independent C generator anchors."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/common/backports"))
from c_source_match import extract_function, find_one, replace_one


class SourceMatchTests(unittest.TestCase):
    def test_exact_anchor_preserves_surrounding_text(self):
        source = "one;\n    count=call(x);\ntwo;\n"
        self.assertEqual(
            replace_one(source, "    count=call(x);", "    count=call(y);"),
            "one;\n    count=call(y);\ntwo;\n",
        )

    def test_whitespace_only_change_and_trailing_newline(self):
        source = "one;\n    value = call(\n        argument);\ntwo;\n"
        result = replace_one(source, "    value=call(argument);\n", "    value = 7;\n")
        self.assertEqual(result, "one;\n    value = 7;\ntwo;\n")

    def test_exact_and_whitespace_variant_are_ambiguous(self):
        with self.assertRaises(ValueError):
            replace_one("x=1; x = 1;", "x=1;", "x=2;")

    def test_missing_anchor_and_identifier_prefix_are_rejected(self):
        for source in ("x=2;", "xx=1;", "/* x=1; */"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                replace_one(source, "x=1;", "x=3;")

    def test_literals_and_comments_are_distinct_tokens(self):
        source = 'const char *s="x=1;"; /* x=1; */\nx = 1;\n'
        self.assertEqual(
            replace_one(source, "x=1;", "x=2;"), 'const char *s="x=1;"; /* x=1; */\nx=2;\n'
        )

    def test_single_exact_text_decoy_in_string_or_comment_is_not_replaced(self):
        for decoy in ('const char *s="x=1;";', "/* x=1; */"):
            source = decoy + "\nx = 1;\n"
            with self.subTest(decoy=decoy):
                self.assertEqual(replace_one(source, "x=1;", "x=2;"), decoy + "\nx=2;\n")

    def test_preprocessor_whitespace_fallback_is_rejected(self):
        with self.assertRaises(ValueError):
            replace_one("#define V(x) (x + 1)\n", "#define V(x) (x+1)", "changed")

    def test_escaped_newline_fallback_is_rejected(self):
        with self.assertRaises(ValueError):
            replace_one("value = a + \\\n b;\n", "value=a+b;", "changed")

    def test_empty_and_comment_changed_anchor_rejected(self):
        for before in ("", "/* old */ x=1;"):
            with self.subTest(before=before), self.assertRaises(ValueError):
                replace_one("/* new */ x=1;", before, "changed")

    def test_function_signature_can_wrap_without_changing_definition(self):
        source = 'static int\nowner(\n    int x)\n{\n    const char *text = "}";\n    /* { */\n    if (x) { return x; }\n    return 0;\n}\nint neighbor(void) { return 2; }\n'
        extracted = extract_function(source, "static int owner(")
        self.assertTrue(extracted.startswith("static int\nowner("))
        self.assertTrue(extracted.endswith("return 0;\n}"))
        self.assertNotIn("neighbor", extracted)

    def test_function_signature_may_include_the_opening_brace(self):
        source = "FRAME_CODE int owner(int x)\n{\n    return x;\n}\nint neighbor(void);\n"
        self.assertEqual(
            extract_function(source, "FRAME_CODE int owner(int x)\n{"),
            "FRAME_CODE int owner(int x)\n{\n    return x;\n}",
        )

    def test_function_signature_decoys_and_ambiguity_are_rejected(self):
        definition = "static int owner(int x) { return x; }"
        source = 'const char *text = "static int owner(";\n/* static int owner( */\n' + definition
        self.assertEqual(extract_function(source, "static int owner("), definition)
        with self.assertRaises(ValueError):
            extract_function(
                definition + "\nstatic int\nowner(int y) { return y; }", "static int owner("
            )

    def test_prototype_cannot_capture_an_unrelated_function_body(self):
        with self.assertRaisesRegex(ValueError, "prototype"):
            extract_function(
                "static int owner(int x);\nint other(void) { return 2; }", "static int owner("
            )

    def test_missing_or_unbalanced_function_body_is_rejected(self):
        for source in ("static int owner(int x)", "static int owner(int x) { return x;"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                extract_function(source, "static int owner(")

    def test_opcode_semantic_span_keeps_all_tokens_and_rejects_changed_values(self):
        expected = "case OP_VALUE:\n    *sp++=JS_DupValue(ctx, value);\n    break;"
        source = "switch(op) { case OP_VALUE: *sp++ = JS_DupValue(\nctx, value); break; }"
        start, end = find_one(source, expected)
        self.assertTrue(source[start:end].startswith("case OP_VALUE:"))
        with self.assertRaises(ValueError):
            find_one(source.replace("ctx, value", "ctx, other"), expected)


if __name__ == "__main__":
    unittest.main()

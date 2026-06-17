import sys, os
sys.path.append( os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) )

import unittest
from lib.template_parser import TemplateVariableParser, ExpressionParser


class ExpressionParserTest(unittest.TestCase):
    def assertExpression(self, text: str, expectedText: str | None = None):
        expr = ExpressionParser.parse(text)
        self.assertEqual(str(expr), expectedText or text)


    def testExpr(self):
        self.assertExpression("")
        self.assertExpression(":")
        self.assertExpression("#")
        self.assertExpression("\\")
        self.assertExpression(r"\:", ":")

    def testExprArgs(self):
        self.assertExpression("var:arg1:arg2")
        self.assertExpression("var:::")

        self.assertExpression("var:arg1#func:funcarg1:funcarg2#func2:func2arg")
        self.assertExpression("var::#f1::###f2#f3:x:")

    def testExprEscape(self):
        self.assertExpression(r"static:\:\#",   "static::#")
        self.assertExpression(r"load:\[a\]",    "load:[a]")
        self.assertExpression(r"load:\[a\\\]", r"load:[a\\]")
        self.assertExpression(r"load:\[\]",     "load:[]")

        self.assertExpression(r"ab\cd\e")       # Don't escape non-stop chars
        self.assertExpression(r"a\nb", "a\nb")  # Allow newline

        self.assertExpression(r"a\:b:c", "a:b:c")

    def testSubExpr(self):
        self.assertExpression("[sub]:arg")
        self.assertExpression("var:[subarg]")
        self.assertExpression("var:arg#[subfunc]")
        self.assertExpression("[subvar]:arg1:arg2#func:[funcsubarg]:funcarg")
        self.assertExpression("[subvar]:[subarg]#[subfunc]:[subfuncarg]")
        self.assertExpression("[subvar:[subsubarg]]:[subvar2:[subsubarg:[subsubsubvar]]]")

    def testSubExprWhitespace(self):
        self.assertExpression("var:  [sub]  ", "var:[sub]")
        self.assertExpression("var:\n[sub]\n", "var:[sub]")

        try:
            self.assertExpression("var:X  [sub]  ")
            self.fail("Expected ValueError")
        except ValueError:
            pass

        try:
            self.assertExpression("var:  [sub]  X")
            self.fail("Expected ValueError")
        except ValueError:
            pass



class TemplateParserTest(unittest.TestCase):
    def assertTemplate(self, template: str, expectedText: str):
        parser = TemplateVariableParser("")
        text = parser.parse(template)
        self.assertEqual(text, expectedText)


    def testParser(self):
        self.assertTemplate(
            "{{static:a, b, c#reverse}}",
            "c, b, a"
        )

    def testParserEscape(self):
        self.assertTemplate(
            r"{{\}}",
            r"{{\}}"
        )

        self.assertTemplate(
            r"{{static:a\\}}",
            r"a\\"
        )

        self.assertTemplate(
            r"{{static:a\}}}",
            r"a}"
        )

        self.assertTemplate(
            r"{{static:a{\}b}}",
            "a{}b"
        )

        # Don't escape non-stop chars
        self.assertTemplate(
            r"{{static:a\bc\de}}",
            r"a\bc\de"
        )

    def testParserEscapeExpr(self):
        self.assertTemplate(
            r"{{static:a\:b:c}}",
            "a:b"
        )

        self.assertTemplate(
            r"{{static:a\:b\:c:d}}",
            "a:b:c"
        )

        self.assertTemplate(
            r"{{static:a\:b\:c:d:e#replace:\::\#}}",
            "a#b#c"
        )

        self.assertTemplate(
            r"{{static:a\[b\[c:d:e#replace:\[:\]}}",
            "a]b]c"
        )

        self.assertTemplate(
            r"{{static:a, b, c#replace:, :\n}}",
            "a\nb\nc"
        )

        self.assertTemplate(
            r"{{static:a\\:b}}",
            r"a\\"
        )

        self.assertTemplate(
            r"{{!\:}}",
            r"{{!:}}"
        )

    def testParserKeepVar(self):
        template = "{{!var:arg#func:funcarg}}"
        self.assertTemplate(template, template)

    def testParserNoVars(self):
        self.assertTemplate("{{}}", "")

        template = "{{}"
        self.assertTemplate(template, template)

        template = "{}}"
        self.assertTemplate(template, template)

        template = "a b {} c {d:e} f"
        self.assertTemplate(template, template)

    def testParserWhitespace(self):
        self.assertTemplate("{{static: a b c #replace: a : A }}", "A b c")
        self.assertTemplate("{{static:a, b, c#replace: :}}", "a,b,c")



if __name__ == "__main__":
    unittest.main(verbosity=2)

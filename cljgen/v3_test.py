"""cljgen v3 acceptance tests — gaps 1-3 closed + v2 mapping preserved.

Run:  python3 v3_test.py
Exit 0 iff every check passes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cljgen import Sym, Kw, Char, Raw, emit, bal_ok, pp, write_forms

FAILURES = []
NCHECKS = 0


def check(name, cond):
    global NCHECKS
    NCHECKS += 1
    print("%-58s %s" % (name, "PASS" if cond else "FAIL"))
    if not cond:
        FAILURES.append(name)


# ---------------------------------------------------------------- gap 1: Raw
check("Raw emits verbatim", emit(Raw("#(+ % 1) xs")) == "#(+ % 1) xs")
check("Raw set literal", emit(Raw("#{:a :b}")) == "#{:a :b}")
check("Raw tagged literal", emit(Raw('#uuid "abc"')) == '#uuid "abc"')
check("Raw var quote", emit(Raw("#'foo")) == "#'foo")
check("Raw inside a form", emit([Sym("map"), Raw("#(+ % 1)"), Sym("xs")])
      == "(map #(+ % 1) xs)")
check("balanced Raw passes bal_ok",
      bal_ok("(def f (map #(+ % 1) xs))"))
try:
    write_forms("/tmp/cljgen_bad_raw.clj",
                [[Sym("def"), Sym("x"), Raw("(unbalanced")]], newlines=False)
    check("unbalanced Raw refused by write_forms", False)
except ValueError:
    check("unbalanced Raw refused by write_forms", True)

# ---------------------------------------------------------------- gap 2: Char
check("Char single delim", emit(Char("(")) == "\\(")
check("Char named", emit(Char("newline")) == "\\newline")
check("Char unicode", emit(Char("u0041")) == "\\u0041")
check("Char plain letter", emit(Char("a")) == "\\a")
check("bal_ok \\( is char not open", bal_ok("(println \\( )"))
check("bal_ok \\) is char not close", bal_ok("(println \\))"))
check("bal_ok \\{ is char not map", bal_ok("(println \\{ )"))
check("bal_ok \\newline named", bal_ok("(println \\newline)"))
check("bal_ok \\space named", bal_ok("(str \\space)"))
check("bal_ok \\u0041 unicode", bal_ok("(println \\u0041)"))
check("bal_ok real char-literal file",
      bal_ok("(defn nl [] \\newline)\n(defn lp [] \\()\n(defn rp [] \\))"))

# ---------------------------------------------------------------- gap 3: pretty
FORMS = [
    [Sym("ns"), Sym("demo.math"), "Docstring with (parens).",
     [Sym("require"),
      [Sym("clojure.string"), Kw(":as"), Sym("str")],
      [Sym("clojure.core")]]],
    [Sym("defn"), Sym("square"), (Sym("n"),), "Returns n squared.",
     (Sym("n"),), [Sym("*"), Sym("n"), Sym("n")]],
    [Sym("def"), Sym("meta"),
     {Kw(":kind"): "vector", Kw(":n"): 3, Kw(":nil-thing"): None,
      Kw(":flag"): True}],
]

one = write_forms("/tmp/cljgen_v3_oneline.clj", FORMS, newlines=False)
check("newlines=False has no newline", "\n" not in one)
check("newlines=False balanced", bal_ok(one))

pretty = write_forms("/tmp/cljgen_v3_pretty.clj", FORMS, newlines=True)
check("pretty output balanced", bal_ok(pretty))
check("pretty output has indentation", "\n  " in pretty)

# force a break with a tiny width to exercise the multi-line path
narrow = pp([Sym("defn"), Sym("f"), (Sym("a"), Sym("b")),
             [Sym("+"), Sym("a"), Sym("b")]], 0, width=10)
check("narrow width forces break", "\n" in narrow)
check("narrow width still balanced", bal_ok(narrow))

# ----------------------------------------------------- v2 mapping preserved
check("list -> ()", emit([Sym("f"), 1]) == "(f 1)")
check("tuple -> []", emit((1, 2)) == "[1 2]")
check("dict -> {}", emit({Kw(":a"): 1}) == "{ :a 1 }")
check("empty list", emit([]) == "()")
check("empty map", emit({}) == "{}")
check("str quoted + escaped", emit('say "hi"') == '"say \\"hi\\""')
check("int", emit(42) == "42")
check("float", emit(0.5) == "0.5")
check("true/false", emit(True) == "true" and emit(False) == "false")
check("none -> nil", emit(None) == "nil")
check("Sym bare", emit(Sym("x.y")) == "x.y")
check("Kw bare", emit(Kw(":x")) == ":x")

print()
if FAILURES:
    print("RESULT: %d FAILURE(S): %s" % (len(FAILURES), FAILURES))
    sys.exit(1)
print("RESULT: ALL %d CHECKS PASS" % NCHECKS)

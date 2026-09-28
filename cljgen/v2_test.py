import sys
sys.path.insert(0, "/home/david/.local/lib/cljgen")
from cljgen import Sym, Kw, write_forms, bal_ok

# A realistic ns built entirely from typed data. newlines=False -> one line.
forms = [
    [Sym("ns"), Sym("demo.math"),
     "Docstring with (parens) [brackets] {braces} and a \"quote\".",
     [Sym("require"),
      [Sym("clojure.string"), Kw(":as"), Sym("str")],
      [Sym("clojure.core")]]],
    [Sym("defn"), Sym("square"), (Sym("n"),), "Returns n squared.",
     (Sym("n"),), [Sym("*"), Sym("n"), Sym("n")]],
    [Sym("defn"), Sym("cube"), (Sym("n"),), "Returns n cubed.",
     (Sym("n"),), [Sym("*"), [Sym("square"), Sym("n")], Sym("n")]],
    [Sym("def"), Sym("ratio"), Kw(":val"), 0.5],
    [Sym("def"), Sym("meta"),
     {Kw(":kind"): "vector", Kw(":n"): 3, Kw(":nil-thing"): None,
      Kw(":flag"): True}],
]

one_line = write_forms("/tmp/v2_oneline.clj", forms, newlines=False)
pretty   = write_forms("/tmp/v2_pretty.clj", forms, newlines=True)

print("=== ONE LINE (newlines=False) ===")
print(one_line)
print()
print("no newline present:", "\n" not in one_line)
print("balanced:", bal_ok(one_line))
print()
print("=== PRETTY (newlines=True) ===")
print(pretty)

# Clojure LLM Tooling

Two tools + one skill for letting an LLM reliably create and edit Clojure/EDN
files **structurally** — never by hand-typing source.

The rule that motivates everything here:

> **An LLM must never hand-emit a `.clj` file.** It authors *data* (a Python
> list of s-expressions), and the tool emits the source with every delimiter
> balanced by construction. To change a file, it names a form by index and the
> tool splices one replacement form in, leaving everything else byte-for-byte
> unchanged.

Two tools, two directions:

| Tool       | Language | Direction                        | When to use                          |
|------------|----------|----------------------------------|--------------------------------------|
| **cljgen** | Python 3 | DATA → `.clj` (emit)             | Create a new file from scratch       |
| **sexpsplice** | Clojure | `.clj` → edit → `.clj` (splice) | Edit one form in an existing file    |

## Status

Production-usable. Both tools ship with formal specs (`SPEC.md`) and acceptance
tests that pass against the real Clojure toolchain (`clj-kondo` + `sexpsplice`),
not just self-consistency checks.

They are complementary: **cljgen** builds new files from typed data; **sexpsplice**
surgically edits existing files while preserving comments, reader macros, and
formatting. Use cljgen to generate, sexpsplice to modify.

```
clojure-llm-tools/
├── README.md            # this file
├── INSTALL.md           # install both tools (Clojure CLI, clj-kondo, launchers)
├── cljgen/              # Python emitter: DATA -> .clj
│   ├── cljgen.py        #   the module (stdlib only, no deps)
│   ├── SPEC.md          #   formal spec + acceptance criteria
│   ├── v2_test.py       #   original regression fixture (still passes)
│   └── v3_test.py       #   acceptance tests (36 checks)
├── sexpsplice/          # Clojure structural editor
│   ├── sexpsplice.clj   #   the tool (9 commands)
│   ├── deps.edn         #   rewrite-clj 1.2.57 + Clojars
│   ├── SPEC.md          #   formal spec + acceptance criteria
│   └── bin/sexpsplice   #   launcher script
└── skills/
    └── clojure-structural-editing/
        └── SKILL.md     # Hermes agent skill (install into ~/.hermes/skills/)
```

## Quick start

```bash
# 1. Install prerequisites (Clojure CLI + clj-kondo) — see INSTALL.md

# 2. Install the sexpsplice launcher on PATH
ln -s "$PWD/sexpsplice/bin/sexpsplice" ~/bin/sexpsplice

# 3. Generate a file with cljgen
python3 - <<'PY'
import sys; sys.path.insert(0, "cljgen")
from cljgen import Sym, Kw, write_forms
forms = [[Sym("ns"), Sym("demo.core")],
         [Sym("defn"), Sym("square"), (Sym("n"),), [Sym("*"), Sym("n"), Sym("n")]]]
write_forms("/tmp/demo.clj", forms, newlines=True)
PY

# 4. Edit it with sexpsplice
sexpsplice list   /tmp/demo.clj
sexpsplice get    /tmp/demo.clj 1
sexpsplice set    /tmp/demo.clj 1 <<< '(defn square [n] (* n n))'
```

## Verification rule (never skip)

Both tools produce source the LLM must **not** trust by eye. Always re-parse
with the real toolchain:

```bash
clj-kondo --lint <file>     # real Clojure reader/linter
sexpsplice list <file>      # real reader, form count
```

## Dependencies & licenses

- **cljgen** — Python 3 standard library only, no dependencies. MIT.
- **sexpsplice** — depends on [rewrite-clj](https://github.com/clj-commons/rewrite-clj)
  (EPL-1.0), fetched from Clojars at runtime. The tool itself is MIT; EPL-1.0 is
  a weak copyleft license that is compatible with an MIT-licensed project.

## License

MIT — see [LICENSE](LICENSE).

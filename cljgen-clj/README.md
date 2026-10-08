# cljgen-clj

Clojure port of the Python `cljgen` — a generator for balanced, loadable
Clojure source from EDN data.

## Why
LLMs that emit Clojure mangle delimiters (unbalanced parens, reversed
lists). `cljgen` takes structured EDN values and produces source that is
**balanced by construction** (a stack-based balance-check gates every write
and refuses to emit unbalanced output).

## Modules
- `cljgen.check` — `balanced?` (delimiter/stack check, string- and
  comment-aware), `check-balance` (file-level), `skip-char-literal`.
- `cljgen.emit` — one value → one-line balanced text.
- `cljgen.pp` — pretty printer (port of the reference algorithm, width-80).
- `cljgen.write` — `write-forms!`: EDN forms → `.clj` file (pretty or one-
  line), balance-gated.
- `cljgen.cli` — `clojure -M -m cljgen.cli <edn-file> <target.clj>`.

## Usage
```
clojure -M -m cljgen.cli forms.edn out.clj     # pretty (default)
```
EDN has no list literal; `write-forms!` maps vectors → lists, except a
1-element vector of a symbol (a parameter/binding vector like `[n]`), which
stays a vector. The whole output is balance-checked before writing.

## Test
Every module is gated by `clj-kondo` (0 errors) and verified byte-exact
against the Python reference (`~/.local/lib/cljgen/cljgen.py`) on its
acceptance battery.

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
cd cljgen-clj && clojure -M -m cljgen.cli forms.edn out.clj     # pretty (default)
```
EDN has no list literal: `write-forms!` maps vectors → lists, EXCEPT (a) a
1-element vector of a symbol (a single-arg parameter vector like `[n]`) and (b)
a `{:__vec__ [...]}` escape map, which emit as vectors `[ ... ]`. **Always use
`{:__vec__ [...]}` for arg/binding vectors** — `(defn add {:__vec__ [a b]}
(+ a b))` → `(defn add [a b] (+ a b))`; a bare multi-element vector would
become a list and emit invalid Clojure. Other escape maps: `{:__raw__ t}` →
verbatim (balance-checked), `{:__char__ n}` → char literal. The whole output is
balance-checked before writing.

## Test
Every module is gated by `clj-kondo` (0 errors) and verified byte-exact
against the Python reference (`cljgen/cljgen.py`) on its acceptance battery.

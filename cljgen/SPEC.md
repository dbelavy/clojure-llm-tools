# cljgen — SPEC

Data-driven Clojure emitter. An LLM authors a Python list of s-expressions;
cljgen emits valid, balanced `.clj` source. Never hand-write Clojure.

Version: v3 (2026-09-28)

---

## Outcomes

1. **Total mapping** — every Python value maps to exactly one Clojure form
   with zero ambiguity. No silent "string might be code" mode.
2. **Balance by construction** — every `( ) [ ] { }` and `" "` is emitted as a
   matched pair. The whole output is re-checked by `bal_ok` before any write;
   an unbalanced result refuses to write.
3. **Raw escape, deliberately named** — reader macros with no data form
   (`#()`, `#{}`, `#uuid`, `#'x`) are emitted via `Raw("...")`. This is the
   *only* verbatim mode, it is explicit and greppable, and it is **still
   balance-checked** as part of the whole output.
4. **Correct char literals** — `Char("...")` emits `\x`, `\newline`,
   `\uXXXX`, `\oXXX`; `bal_ok` parses the full Clojure char-literal grammar
   instead of naively skipping 2 chars.
5. **Pretty printing** — `write_forms(newlines=True)` emits an indent-aware,
   width-bounded layout; `newlines=False` stays a single line (v2-identical).

---

## Total mapping

| Python value          | Clojure emitted          |
|-----------------------|--------------------------|
| `list`                | `( child child ... )`    |
| `tuple`               | `[ child child ... ]`    |
| `dict`                | `{ k v k v ... }`        |
| `str`                 | `"escaped"`              |
| `int` / `float`       | decimal                  |
| `True` / `False`      | `true` / `false`         |
| `None`                | `nil`                    |
| `Sym("x.y")`          | `x.y`                    |
| `Kw("x")`             | `:x`                     |
| `Char("newline")`     | `\newline`               |
| `Raw("#(+ % 1) xs")`  | `#(+ % 1) xs` (verbatim) |

- A docstring is a `str` in the docstring position → a quoted string.
- A `[n]` params block is a `tuple` → a vector.
- Symbols are `Sym(...)`; keywords are `Kw(...)`.
- `Raw` is the only verbatim mode; it is balance-checked.

---

## Acceptance criteria

All enforced by `v3_test.py` (36 checks, exit 0). Plus a real-parser check:

- `clj-kondo --lint <file>` parses the emitted file with no **syntax** errors
  (semantic lint warnings about demo data are expected).
- `sexpsplice list <file>` reads the emitted file into the expected top-level
  forms.

1. `Raw("...")` emits verbatim and passes `bal_ok` when balanced; an
   unbalanced `Raw` makes `write_forms` raise `ValueError`.
2. `Char("(")`, `Char("newline")`, `Char("u0041")` emit correctly; `bal_ok`
   treats `\(`, `\)`, `\{`, `\newline`, `\space`, `\uXXXX` as char literals,
   not delimiters.
3. `write_forms(newlines=True)` output is balanced and indented; a narrow
   `width` forces a multi-line break that is still balanced.
4. `write_forms(newlines=False)` contains no `\n` and is byte-identical to v2.
5. The v2 mapping (list/tuple/dict/str/int/float/bool/None/Sym/Kw) is
   unchanged.

---

## Non-goals

- **No data reader** (`.clj` → Python) in this version. Emit-only.
- **No JSON wrapper.** Callers construct Python data directly.
- **No `Raw` validation beyond balance.** `Raw` may contain any text; it is
  not parsed. Balance is the safety net, not a reader.
- **No comments in output.** Use the structural editor (sexpsplice) to add
  them post-hoc.
- **No round-trip guarantee.** Emit → read is not lossless for `Raw`/`Char`.

---

## Layout

- `cljgen.py` — the module (no dependencies, stdlib only).
- `v3_test.py` — acceptance tests.
- `v2_test.py` — original regression fixture (still passes).

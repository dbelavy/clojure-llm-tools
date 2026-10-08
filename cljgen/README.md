# cljgen — DATA → Clojure emitter (Python)

An LLM authors a Python list of s-expressions; cljgen emits valid, balanced
`.clj` source. Never hand-write Clojure.

See `SPEC.md` for the formal spec and acceptance criteria.

## Why

LLMs are unreliable at emitting balanced Clojure by hand. Every `( ) [ ] { }`
and `" "` is inserted by this module as a matched pair, so output is balanced
by construction, then re-checked by `bal_ok` before any write.

## Mapping (total, unambiguous)

| Python          | Clojure         |
|-----------------|-----------------|
| `list`          | `( ... )`       |
| `tuple`         | `[ ... ]`       |
| `dict`          | `{ k v ... }`   |
| `str`           | `"..."`         |
| `int`/`float`   | decimal         |
| `True`/`False`  | `true`/`false`  |
| `None`          | `nil`           |
| `Sym("x")`      | `x`             |
| `Kw("x")`       | `:x`            |
| `Char("newline")` | `\newline`    |
| `Raw("#(+ % 1) xs")` | `#(+ % 1) xs` (verbatim, balance-checked) |

`Raw` is the *only* verbatim mode, and it is deliberately named and
balance-checked — reader macros (`#()`, `#{}`, `#uuid`, `#'x`) go through it,
never through a plain string.

### The one trap: don't invert the mapping

The recurring mistake is putting the *right values in the wrong Python type*:

- **Binding / arg vectors are ONE flat `tuple`, not a list of pairs.**
  `(let [a 1 b 2] body)` is `[Sym("let"), (Sym("a"), 1, Sym("b"), 2), body]` —
  a single tuple of alternating name/value, NOT `[(Sym("a"), 1), (Sym("b"), 2)]`
  (that emits a vector of two nested vectors). A `defn` arg vector is `(Sym("n"),)`.
- **`(atom nil)` is a LIST call** — `[Sym("atom"), None]` emits `(atom nil)` (a
  form), not a vector.
- **A form's head is a `Sym`, its body is a `list`.** `(def x 1)` is
  `[Sym("def"), Sym("x"), 1]`. clj-kondo localises each inversion cheaply, so
  generate then lint; but keep the flat-tuple rule in mind when authoring.

## Usage

```python
import sys; sys.path.insert(0, "/path/to/cljgen")
from cljgen import Sym, Kw, Char, Raw, write_forms

forms = [
    [Sym("ns"), Sym("demo.math"), "Docstring.",
     [Sym("require"), [Sym("clojure.string"), Kw(":as"), Sym("str")]]],
    [Sym("defn"), Sym("square"), (Sym("n"),), "Returns n squared.",
     (Sym("n"),), [Sym("*"), Sym("n"), Sym("n")]],
    [Sym("def"), Sym("evens"), [Sym("filter"), Raw("#(even? %)"),
                                [Sym("range"), 10]]],
]

write_forms("/path/target.clj", forms, newlines=True)   # pretty, balanced
write_forms("/path/one.clj",     forms, newlines=False)  # single line

# then verify with the real parser (never trust your own eyes):
#   clj-kondo --lint /path/target.clj
#   sexpsplice list /path/target.clj
```

## API

- `emit(x, where="root") -> str` — one value to a single-line form.
- `pp(x, col=0, width=80) -> str` — indent-aware pretty print.
- `write_forms(path, forms, newlines=True, width=80) -> str` — write top-level
  forms; `newlines=False` emits a single line; refuses to write if unbalanced.
- `bal_ok(s) -> bool` — delimiter-balance check (respects strings, char
  literals, `;` comments).
- Types: `Sym`, `Kw`, `Char`, `Raw`.

## Tests

```bash
python3 v3_test.py   # 36 acceptance checks, exit 0
python3 v2_test.py   # original regression fixture
```

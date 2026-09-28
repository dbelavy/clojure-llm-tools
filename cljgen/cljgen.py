"""cljgen v3 — build .clj from typed DATA. The only Clojure emitter you need.

v2 -> v3 (2026-09-28) — three gaps closed:
  1. Raw(...)  — a deliberately-named raw escape for reader macros that have
     no data representation: #(), #{}, #uuid "...", #'x. Emitted VERBATIM,
     exempt from the total mapping, but STILL balance-checked (bal_ok scans
     the whole output, so an unbalanced Raw aborts the write).
  2. Char(...) — a Clojure character literal: Char('newline') -> \\newline,
     Char('(') -> \\(. bal_ok now parses the full char-literal grammar
     (single-char, \\newline \\space \\tab \\return \\backspace \\formfeed,
     \\uXXXX, \\oXXX) instead of naively skipping 2 chars.
  3. Pretty printer — write_forms(newlines=True) now emits an indent-aware,
     width-bounded layout instead of one form per line.

WHY THIS EXISTS (2026-09-27)
-----------------------------
LLMs are unreliable at emitting balanced Clojure by hand. The rule:
NEVER hand-write a .clj. Build it as Python DATA and let this module emit
the source. Every ( ) [ ] { } and every " " is inserted by THIS tool as a
matched pair, so the output is balanced by construction. You author a
vector of s-expressions; the tool emits valid Clojure.

TOTAL MAPPING — everything is explicit:
    Python value        ->  Clojure emitted
    ------------------    --------------------------------
    list                ->  ( child child ... )      a list / form
    tuple               ->  [ child child ... ]      a vector
    dict                ->  { k v k v ... }          a map
    str                 ->  "escaped"                a STRING LITERAL
    int / float         ->  decimal
    True / False        ->  true / false
    None                ->  nil
    Sym("x.y")          ->  x.y                      a SYMBOL (bare)
    Kw("x")             ->  :x                       a KEYWORD (bare)
    Char("newline")     ->  \\newline                 a CHARACTER literal
    Raw("#(+ % 1) xs")  ->  #(+ % 1) xs              VERBATIM (balance-checked)

A docstring is just a `str` in the docstring position -> emitted as a
"quoted" string, exactly right. A `[n]` params block is a `tuple` ->
emitted as a vector. Symbols (`defn`, `square`, `n`) are `Sym(...)`.
Raw is the ONLY verbatim mode, and it is deliberately named + balance-
checked, so you can never accidentally emit an unquoted docstring or a
list where a vector is required.

USAGE
-----
    import sys; sys.path.insert(0, "/home/david/.local/lib/cljgen")
    from cljgen import Sym, Kw, Char, Raw
    forms = [
        [Sym("ns"), Sym("demo.math"), "A doc (string) with (parens).",
         [Sym("require"), [Sym("clojure.string"), Kw(":as"), Sym("str")]]],
        [Sym("defn"), Sym("square"), (Sym("n"),), "Returns n squared.",
         (Sym("n"),), [Sym("*"), Sym("n"), Sym("n")]],
    ]
    cljgen.write_forms("/path/target.clj", forms, newlines=True)
    # then VERIFY with the real parser (never trust your own eyes):
    #   clj-kondo --lint /path/target.clj
    #   sexpsplice list /path/target.clj
"""

_OPEN  = "([{"
_CLOSE = ")]}"
_ESC   = {'"': '\\"', "\\": "\\\\", "\n": "\\n", "\t": "\\t",
          "\r": "\\r", "\f": "\\f"}

# Clojure named character literals, longest first so startswith is exact.
_NAMED_CHARS = ("newline", "space", "tab", "return", "backspace", "formfeed")


class Sym:
    """A Clojure symbol, emitted bare: Sym('x.y') -> x.y"""
    __slots__ = ("name",)
    def __init__(self, name):
        self.name = str(name)
    def __repr__(self):
        return "Sym(%r)" % self.name


class Kw:
    """A Clojure keyword, emitted as :name: Kw('x') -> :x"""
    __slots__ = ("name",)
    def __init__(self, name):
        self.name = str(name).lstrip(":")
    def __repr__(self):
        return "Kw(%r)" % self.name


class Char:
    """A Clojure character literal: Char('newline') -> \\newline,
    Char('(') -> \\(, Char('u0041') -> \\u0041."""
    __slots__ = ("name",)
    def __init__(self, name):
        self.name = str(name)
    def __repr__(self):
        return "Char(%r)" % self.name


class Raw:
    """A deliberately-named raw escape for reader macros with no data form:
    Raw('#(+ % 1) xs'), Raw('#{:a :b}'), Raw('#uuid "..."'). Emitted VERBATIM,
    exempt from the total mapping, but STILL balance-checked by bal_ok over
    the whole output — an unbalanced Raw aborts the write like anything else."""
    __slots__ = ("text",)
    def __init__(self, text):
        self.text = str(text)
    def __repr__(self):
        return "Raw(%r)" % self.text


def escape(s):
    return "".join(_ESC.get(c, c) for c in s)


def emit(x, where="root"):
    """Serialize one value to balanced Clojure source (a single string)."""
    if x is None:
        return "nil"
    if x is True:
        return "true"
    if x is False:
        return "false"
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return str(x)
    if isinstance(x, str):
        return '"' + escape(x) + '"'
    if isinstance(x, Sym):
        return x.name
    if isinstance(x, Kw):
        return ":" + x.name
    if isinstance(x, Char):
        return "\\" + x.name
    if isinstance(x, Raw):
        return x.text
    if isinstance(x, (list, tuple)):
        kind = _OPEN[0] if isinstance(x, list) else _OPEN[1]   # ( vs [
        close = ")" if isinstance(x, list) else "]"
        if not x:
            return kind + close
        return kind + " ".join(emit(c, where) for c in x) + close
    if isinstance(x, dict):
        if not x:
            return "{}"
        return "{ " + " ".join(
            emit(k, where) + " " + emit(v, where)
            for k, v in x.items()) + " }"
    raise TypeError("not a cljgen value at %s: %r" % (where, type(x).__name__))


def _is_atom(x):
    return not isinstance(x, (list, tuple, dict))


def pp(x, col=0, width=80):
    """Indent-aware pretty printer. Renders x assuming the cursor sits at
    column `col`. Forms that fit within `width` stay on one line; otherwise
    the children break onto lines indented 2 spaces per nesting level, with
    the closing delimiter on its own line at the opening column."""
    if _is_atom(x):
        return emit(x)
    if isinstance(x, (list, tuple)):
        op, cl = ("(", ")") if isinstance(x, list) else ("[", "]")
        if not x:
            return op + cl
        one = emit(x)
        if col + len(one) <= width:
            return one
        inner = "\n".join(" " * (col + 2) + pp(c, col + 2, width) for c in x)
        return op + "\n" + inner + "\n" + " " * col + cl
    if isinstance(x, dict):
        if not x:
            return "{}"
        one = emit(x)
        if col + len(one) <= width:
            return one
        inner = "\n".join(
            " " * (col + 2) + emit(k) + " " + pp(v, col + 2 + len(emit(k)) + 1, width)
            for k, v in x.items())
        return "{" + "\n" + inner + "\n" + " " * col + "}"
    return emit(x)


def write_forms(path, forms, newlines=True, width=80):
    """Serialize top-level `forms` to `path`.

    `newlines=False` emits a single line (no \\n anywhere) — byte-identical
    to v2. `newlines=True` emits an indent-aware pretty layout. Refuses to
    write if the whole output is unbalanced."""
    if newlines:
        parts = [pp(f, 0, width) for f in forms]
        text = "\n\n".join(parts) + "\n"
    else:
        parts = [emit(f, "form %d" % i) for i, f in enumerate(forms)]
        text = " ".join(parts)
    if not bal_ok(text):
        raise ValueError("emitted file unbalanced — refused to write " + path)
    with open(path, "w") as fh:
        fh.write(text)
    return text


def _skip_char_literal(s, i, n):
    """s[i] == '\\\\'. Return the index just past the Clojure char literal:
    \\x (single char), \\newline (named), \\uXXXX, or \\oXXX."""
    i += 1                                   # the backslash
    if i >= n:
        return i
    for name in _NAMED_CHARS:
        if s.startswith(name, i):
            return i + len(name)
    c = s[i]
    if c == "u":                             # \uXXXX — 4 hex digits
        j = i + 1
        while j < n and j < i + 5 and s[j] in "0123456789abcdefABCDEF":
            j += 1
        return j
    if c == "o":                             # \oXXX — 1-3 octal digits
        j = i + 1
        while j < n and j < i + 4 and s[j] in "01234567":
            j += 1
        return j
    return i + 1                             # single char, incl. ( ) [ ] { } "


def bal_ok(s):
    """True iff every ( ) [ ] { } is balanced and nested, respecting
    string-literal, char-literal, and ; comment contents."""
    stack, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == ";":
            j = s.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            i = j + 1
            continue
        if c == "\\":
            i = _skip_char_literal(s, i, n)
            continue
        if c in _OPEN:
            stack.append(c)
        elif c in _CLOSE:
            if not stack or _OPEN[_CLOSE.index(c)] != stack.pop():
                return False
        i += 1
    return not stack

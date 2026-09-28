# sexpsplice — Clojure structural editor

Edit `.clj`/`.edn` files **structurally**, not textually. Name a form by index,
supply one replacement form; the tool parses with a real reader and splices it
in, leaving every other form byte-for-byte unchanged — comments, reader macros
(`#()`, `#{}`), and formatting all survive.

See `SPEC.md` for the formal spec and acceptance criteria.

## Commands

```
sexpsplice list   <file>               list top-level forms (index + 60-char preview)
sexpsplice get    <file> <path>        FULL node at path (no truncation)
sexpsplice set    <file> <path>        replace node at path with ONE form from stdin
sexpsplice append <file>               append ONE form from stdin (top-level)
sexpsplice delete <file> <path>        remove the node at path
sexpsplice apply  <file>               batch edits from stdin (EDN vector), atomic
sexpsplice find   <file> <substring>   list forms containing substring (case-insensitive)
sexpsplice move   <file> <from> <to>   move top-level form FROM to final index TO
sexpsplice insert <file> <idx>         insert ONE form from stdin at index IDX
```

Flags (anywhere): `--dry-run`/`-n` prints the would-be result without writing;
`--no-backup` skips the `.bak` backup.

## Path syntax

A vector of selectors, each descending one level:

- integer → Nth value child (0-based; whitespace/comments skipped)
- keyword → map value at key `:k`

Examples: `[2]` = top-level form 2; `[1 3]` = form 1's 3rd child (a defn body);
`[3 2 :port]` = form 3 → 2nd child (a map) → value at `:port`. A bare integer
is shorthand for `[n]`.

## apply (atomic batch)

stdin carries an EDN vector of op maps:

```
[{:op :set :path [2] :form "(def beta 43)"}
 {:op :append :form "(def d 1)"}
 {:op :delete :path [3]}]
```

All ops apply atomically — any error mid-batch aborts with no write, exit 1.

## Why this shape

- **LLM types one form**, the tool parses with a real reader and emits all
  delimiters — balanced by construction.
- **rewrite-clj** preserves untouched forms byte-for-byte. Do NOT re-serialize
  with `pr-str`: it expands `#(+ % 1)` into `(fn* [p1__142#] ...)`, drops
  comments, reorders sets.

## Dependency

rewrite-clj **1.2.57** from **Clojars** (not Maven Central — and `1.3.8` does
not exist). `deps.edn` carries the explicit Clojars repo. Uses plain
`clojure -M`, not babashka (whose SCI preprocessor breaks the reader on some
hosts).

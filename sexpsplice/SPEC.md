# sexpsplice — Specification

Structural S-expression editor for `.clj`/`.edn` files, built for LLM agents
(and humans). An agent types ONE form and names its target by index or path;
sexpsplice parses with a real reader (rewrite-clj) and splices it in, leaving
every untouched byte — comments, reader macros (`#()`, `#{}`), formatting —
intact.

## Model

- A file is a **nested S-expression tree**.
- **Top-level forms** are indexed 0..N (the value children of the root).
- A **path** addresses any node: a vector of selectors, each descending one level.
- A **"value child"** = a child that is neither whitespace nor comment.

## Path syntax

A path is a vector; each selector is applied left-to-right, descending one level:

| selector | meaning |
|----------|---------|
| integer  | the Nth value child (0-based, whitespace/comments skipped) |
| keyword  | the value of key `:k` in a map (descends to the value node) |

A bare integer argument is shorthand for `[n]` (backward compatible).

Examples (for `(defn f [z] (inc z))`, value children are `defn`=0, `f`=1, `[z]`=2, body=3):

```
get  foo.clj [2]           top-level form 2
get  foo.clj [2 3]         form 2's 3rd value child (the defn body)
set  foo.clj [0 2 :port]   set :port in the map that is form 0's child 2
delete foo.clj [1 2 0]     delete a nested node
```

## Commands

```
list   <file>               list top-level forms (index + 60-char preview)
get    <file> <path>        print the node at PATH (full text)
set    <file> <path>        replace node at PATH with ONE form from stdin
append <file>               append ONE form from stdin
delete <file> <path>        remove the node at PATH
apply  <file>               batch of edits from stdin (EDN vector, atomic)
find   <file> <substring>   list forms containing substring (case-insensitive)
move   <file> <from> <to>   move top-level form FROM to final index TO
insert <file> <idx>         insert ONE form from stdin at top-level index IDX
```

### `apply` (stdin, EDN vector of ops)

```
[{:op :set :path [2] :form "(def beta 43)"}
 {:op :append :form "(def delta 1)"}
 {:op :delete :path [3]}]
```

All ops apply to the root tree in sequence, in ONE parse + ONE write.
Any error (bad path, bad form, unknown op) → **no write at all**, exit 1.

### `move <from> <to>`

Moves the top-level form at index `from` to final index `to` (0..N-1). All
other forms keep their relative order. The form's leading comment block
(doc comments immediately above it) moves with it. `from == to` is a no-op.

### `insert <idx>`

Inserts one form (stdin) at top-level index `idx` (0..N; N = append). The
existing form at `idx` and everything after shifts down.

## Flags

- `--dry-run` / `-n` — compute the result and print it to stdout; do NOT write.
- `--no-backup` — skip the `.bak` backup (see invariants).

Flags may appear before or after the command name.

## Invariants

1. **Byte preservation**: `set`/`delete`/`append`/`apply` preserve every
   untouched byte exactly. `move`/`insert` preserve each form's content and
   its leading comments byte-for-byte, but canonicalize the top-level
   inter-form separator to single newlines.
2. **Reader macros survive**: `#(+ % 1)` is never expanded to `(fn* ...)`.
3. **Comments are never silently deleted**: `delete` removes only the form +
   a newline; an orphaned comment is left for deliberate cleanup. `move`
   carries a form's leading comments with it.
4. **Atomic writes**: every write goes to a temp file in the same directory,
   then `Files/move` with `REPLACE_EXISTING` (ATOMIC_MOVE where supported) —
   no torn writes.
5. **Backup**: before writing, the current file is copied to `<file>.bak`
   (the last-known-good state). Disable with `--no-backup`.
6. **Errors exit 1** with a message on stderr; success prints `OK: ...`.

## Outcomes (acceptance criteria)

- [ ] `list` shows correct indices (comments skipped, never counted as forms)
- [ ] `get` prints the full node, no truncation
- [ ] `get`/`set`/`delete` resolve nested paths (integer + keyword selectors)
- [ ] `set`/`delete`/`append`/`apply` preserve comments + reader macros
      (`grep -c 'fn\*'` = 0, `grep -c '#('` preserved)
- [ ] `append` produces clean single-newline separation + trailing newline,
      including on an empty file (no leading blank line)
- [ ] `delete` leaves no blank line; deleting the only form yields a 1-byte
      file (single trailing newline)
- [ ] `apply` batch: mixed set/append/delete in one write; bad path mid-batch
      aborts with the file byte-for-byte unchanged
- [ ] `find` returns matching indices; no match → exit 1 with a message
- [ ] `move from to` lands the form at the final index; leading comment moves
      with it; `from==to` is a no-op; out-of-range exits 1
- [ ] `insert idx` at 0/mid/end produces clean single-newline separation
- [ ] `--dry-run` prints the would-be content and does NOT modify the file
- [ ] writes create `<file>.bak`; `--no-backup` suppresses it
- [ ] out-of-range path / bad-stdin / no-args all exit 1 with the right message
- [ ] `clj-kondo --lint` = 0 errors, 0 warnings

## Non-goals (deliberately out of scope)

- `rename` — a def symbol rename is `set [idx 1]` (the name is value child 1);
  a dedicated command would need cross-reference resolution (footgun).
- Nested `move`/`insert` — reordering nested children is rare; the block model
  with comment attachment only applies cleanly at top level.
- Regex search — `find` is case-insensitive substring (regex escaping is a
  footgun for LLMs).

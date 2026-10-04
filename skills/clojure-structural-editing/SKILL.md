---
name: clojure-structural-editing
description: "Use when authoring or editing Clojure/EDN (.clj/.cljs) code. Create files with cljgen (data to .clj) or the sexpsplice append loop; edit by form index via sexpsplice. Never hand-edit with sed/python/pr-str."
version: 1.2.0
author: Richard Kimble
license: MIT
metadata:
  hermes:
    tags: [Clojure, EDN, clj, cljs, coding, authoring, writing, structural-editing, sexpsplice, cljgen, rewrite-clj]
    category: software-development
---

# Clojure Coding & Structural Editing (cljgen + sexpsplice)

Author and edit `.clj`/`.edn` files **structurally**, never textually. Two tools:

- **Author** (build a file): `cljgen` (Python, data → `.clj`) or the `sexpsplice append` loop — add one form at a time.
- **Edit** (change an existing file): `sexpsplice` by form index — name a form, supply one replacement, everything else is preserved **byte-for-byte** (comments, reader macros `#()`/`#{}`, formatting all survive).

Never hand-edit Clojure with sed, python string munging, or `pr-str` — those corrupt delimiters, expand reader macros into `(fn* ...)`, and drop comments.

## When to Use

- **Authoring**: an LLM (or human) needs to *create* a Clojure file from scratch — use cljgen, or the `sexpsplice append` loop (one form at a time, review each).
- **Editing**: an LLM needs to change one form in an existing Clojure file without retyping the whole file (which corrupts delimiters/formatting).
- You want delimiters guaranteed balanced by construction (the parser emits them).
- You need comment/reader-macro preservation — where `pr-str` re-serialization fails.
- You find yourself about to use sed/python/pr-str on a `.clj` file — stop, and use this instead.

## Authoring workflow — build a file incrementally (append → review)

The canonical way to author a `.clj` file from scratch, ONE form at a time.
Never batch many forms at once, and never hand-edit with sed/python/pr-str.

1. Start empty:  `: > demo.clj`
2. Add ONE expression:  `echo '(ns demo.core)' | sexpsplice append demo.clj`
3. Write + review:  `sexpsplice list demo.clj && clj-kondo --lint demo.clj`
4. Repeat: add one more form, review, add one more, review …

Every `append` is parsed by a real Clojure reader (delimiters balanced by
construction), writes atomically, and leaves `<file>.bak`. Reviewing after
EACH form means a malformed form is caught immediately while the file is
still small, and the fix is a single `sexpsplice delete <file> <idx>`.

To CHANGE an existing form (not add), use `set`/`delete`/`move`/`insert` by
index — locate a form with `sexpsplice find <file> <substring>`.

## The tool

- **`sexpsplice`** — launcher at `~/bin/sexpsplice`, source at `~/projects/sexpsplice/sexpsplice.clj` (plus `deps.edn`). Canonical repo: `~/projects/clojure-llm-tools/` (contains both tools + docs + this skill).
- **`cljgen`** — the emit-side companion (Python): build `.clj` from typed data. Use it to *create* files; use sexpsplice to *edit* them. See `~/projects/clojure-llm-tools/cljgen/`.

**cljgen collection mapping — the one trap to internalise.** The Python→Clojure mapping is exact: `list` → `( ... )` form, `tuple` → `[ ... ]` vector, `dict` → map, `Sym("x")` → bare symbol, `Raw("...")` → verbatim (balance-checked). The trap is *inverting* which Python type goes where:

- **Binding/arg vectors are ONE flat `tuple`, not a list of pairs.** `(let [a 1 b 2] ...)` is written `[Sym("let"), (Sym("a"), 1, Sym("b"), 2), <body>]` — a single tuple of alternating name/value, NOT `[(Sym("a"), 1), (Sym("b"), 2)]` (that would emit a vector of two nested vectors). Same for a `defn` arg vector: `(Sym("n"),)`.
- **`(atom nil)` is a LIST call**, not a special form — write `[Sym("atom"), None]`, which emits `(atom nil)` (a form), correctly distinct from `[ ... ]`.
- **A form's head is a `Sym`, its body is a `list`.** `(def square ...)` → `[Sym("def"), Sym("square"), ...]`. Getting the head/body nesting right is the whole game; clj-kondo localises each inversion cheaply, but a worked example (see `cljgen/cljgen.py` docstring `USAGE`, lines 45–59) saves re-deriving it.
- **`clj-kondo`** — installed at `~/.local/bin/clj-kondo` for lint verification.

### Commands

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

Flags (anywhere): `--dry-run`/`-n` prints the would-be result without writing; `--no-backup` skips the `.bak` backup.

**Two `move`/`insert` behaviours to know before you use them:**
- **`move` canonicalises inter-form separators.** It collapses blank lines *between* top-level forms to single newlines (the block model drops whitespace and re-emits with `n/newlines 1` separators). A form's *own* internal content — including blank lines inside it — is preserved byte-for-byte. So `(def b\n\n  2)` keeps its internal blank line, but the gap between `(def a 1)` and `(def b ...)` does not survive a `move`. If you need whitespace exactly preserved, use `set` (which is byte-preserving), not `move`.
- **`insert` at the same index stacks in REVERSE.** Each `insert` places its form *at* index N and pushes existing forms down, so three `insert idx 0` calls land as C, B, A (reverse of insertion order). To insert several forms in forward order at the front, insert them in reverse, or `append` then `move` (chained moves fix ordering).

**Path syntax** = vector of selectors, each descending one level:
- integer → Nth value child (0-based, whitespace/comments skipped)
- keyword → map value at key `:k`
Examples: `[2]` = top-level form 2; `[1 3]` = form 1's 3rd child (a defn body); `[3 2 :port]` = form 3 → its 2nd child (a map) → value at `:port`. A bare integer is shorthand for `[n]`.

**apply** (stdin, EDN vector): `[{:op :set :path [2] :form "(def beta 43)"} {:op :append :form "(def d 1)"} {:op :delete :path [3]}]`. All ops apply atomically — any error → no write, exit 1.

Full CRUD + batch + discover/reorder: create (append/insert), read (list + get + find), update (set), delete (delete), transactional multi-edit (apply), reorder (move).

The **spec** lives at `~/projects/sexpsplice/SPEC.md` (commands, path syntax, invariants, acceptance criteria, non-goals). Read it before extending.

stdin carries exactly one form. Errors exit 1: `no readable form on stdin`, `index <i> out of range 0-<N-1>`, `cannot parse file <file>`.

## The technique (why this shape)

- **LLM types one form**, the tool parses it with a real reader and emits all delimiters — balanced by construction. "Edit by location number" workflow.
- **rewrite-clj** (the parser/serializer) preserves untouched forms byte-for-byte. Do NOT re-serialize with `pr-str`: it expands `#(+ % 1)` into `(fn* [p1__142#] ...)`, drops comments, and reorders sets.

## Critical implementation gotchas

1. **Reader idiom**: 2-arg `(read r :eof)` throws ClassCastException (Keyword → PushbackReader). The 2-arg form's second arg is a *read-at position*, not an eof sentinel. Correct: `(read {:eof ::eof} r)` — pass an opts **map** with `:eof`.
2. **Top-level child layout is NOT even/odd.** `p/parse-string-all` returns a `FormsNode` whose children interleave forms, whitespace, and comments, and a `CommentNode` **absorbs its trailing newline** (so the next form immediately follows the comment node — no separate newline node). Index forms by scanning for children that are neither `n/whitespace?` nor `n/comment?`, tracking their real child indices.
3. **Append separator**: strip trailing whitespace nodes first, then `conj` `(n/newlines 1) new-node (n/newlines 1)` so you fully control the separator and trailing newline.
4. **Delete uses plain `z/remove`, not `z/remove-preserve-newline`.** `remove-preserve-newline` keeps the newline (for nested edits), which leaves a blank line at top level. Plain `z/remove` strips the node + its trailing newline — clean for top-level forms.
5. **Navigation: UNSTARRED `z/down`/`z/right` skip whitespace+comments; STARRED `z/down*`/`z/right*` are raw moves that land ON whitespace.** For path navigation always use unstarred. (This is the opposite of what the names suggest at first glance.)
6. **`z/root` returns a NODE, not a loc — `z/up` returns a loc.** To get back to the root *loc* after an edit (needed when chaining batch ops), walk `z/up` to the top (`to-root`), don't use `z/root`.
7. **Batch `apply` must resolve each op against the ROOT, not the previous op's result loc.** After `z/replace`/`z/remove` the loc is positioned at the edited node; the next op's path would resolve relative to that node. Wrap each op's result in `to-root` so every path resolves from the root.
8. **Comments are never deleted** — `delete` removes only the form + a newline; an orphaned comment (e.g. a `;; docs beta` line whose form was deleted) is left in place for the human/LLM to clean up deliberately.
9. **Rewrite-clj is on Clojars, not Maven Central**, and version `1.3.8` does not exist — pin `1.2.57`. deps.edn needs an explicit `clojars` repo (`:mvn/repos {"clojars" {:url "https://repo.clojars.org/"}}`).
10. **babashka SCI breaks `read`/`clojure.tools.reader`/`edamame`** on some hosts (the peer hit this). Use plain `clojure -M`, not `bb`, for reader correctness.
11. **Java NIO varargs**: `Files/exists`, `Files/write`, and `Files/createTempFile` have NO no-varargs overload in Clojure — always pass the trailing array: `(Files/write tmp bytes (into-array java.nio.file.OpenOption []))`, `(Files/exists src (into-array java.nio.file.LinkOption []))`, `(Files/createTempFile dir ".pre-" ".suf" (into-array java.nio.file.attribute.FileAttribute []))`. Compilation fails at runtime with "No matching method ... taking N args" otherwise.
12. **Atomic write = temp file in same dir + `Files/move` with `ATOMIC_MOVE` (fallback to `REPLACE_EXISTING`)**, and backup to `<file>.bak` first. Use the fallback because ATOMIC_MOVE throws on some filesystems. Do NOT `spit` directly.
13. **`move`/`insert` use a block model, not the zipper**: `form-blocks` splits top-level children into `[leading-comments..., form]` blocks (comments attach to the FOLLOWING form — doc convention), drops whitespace, and `emit-string` re-renders with single-newline separators. This is deliberately canonicalizing (unlike `set`/`delete`/`append` which preserve bytes).

## Verification checklist

- [ ] `sexpsplice list` shows correct index count (comments skipped, not counted as forms)
- [ ] `get` prints the full form (no 60-char truncation)
- [ ] `set` leaves comments + reader macros intact (`grep -c 'fn\*'` = 0, `grep -c '#('` preserved)
- [ ] `append` produces clean single-newline separation + trailing newline
- [ ] `delete` leaves no blank line (first/middle/last form all tidy); deleting the only form yields a 1-byte file (single trailing newline)
- [ ] out-of-range path / bad-stdin / no-args all exit 1 with the right message (`path [...] does not resolve`, `no readable form on stdin`)
- [ ] `apply` batch: mixed set/append/delete in one call writes once; a bad path mid-batch aborts with the file unchanged (atomic)
- [ ] `find` returns matching indices; no match → exit 1 with a message
- [ ] `move` lands the form at the final index; leading doc-comment travels with it; `from==to` is a no-op; out-of-range exits 1
- [ ] `insert` at 0/mid/end (and empty file) produces clean single-newline separation
- [ ] `--dry-run` prints the would-be result and leaves the file untouched; `--no-backup` suppresses `.bak`; a real write creates `<file>.bak`
- [ ] `clj-kondo --lint` = 0 errors (disable `:namespace-name-mismatch` for test namespaces)

## Setup notes

- Project: `~/projects/sexpsplice/` with `deps.edn` (`:aliases {:run {:main-opts ["sexpsplice.clj"]}}`).
- Launcher `~/bin/sexpsplice` runs `clojure -Srepro -Sdeps '<deps>' -M sexpsplice.clj "$@"`; `SEXPSPLICE_HOME` overrides the project dir.
- clj-kondo install: `curl -sL https://github.com/clj-kondo/clj-kondo/releases/download/v<VER>/clj-kondo-<VER>-linux-amd64.zip` (asset name has NO `v` prefix — `clj-kondo-2026.08.04-linux-amd64.zip`, not `.../latest/download/...`).

---
name: clojure-programming
category: software-development
description: "Use for writing or editing Clojure/EDN: cljgen + sexpsplice. Idiomatic pure functional style, -> / ->> threading, strict tool-verified paren balance."
version: 1.7.0
author: Richard Kimble (renamed clojure-structural-editing → clojure-programming by David, 2026-09-28)
license: MIT
metadata:
  hermes:
    tags: [Clojure, EDN, clj, cljs, coding, authoring, writing, editing, debugging, structural-editing, sexpsplice, cljgen, rewrite-clj]
    category: software-development
---

# Clojure Programming (cljgen + sexpsplice)

Author and edit `.clj`/`.edn` files **structurally**, never textually. Two **Clojure** tools:

- **Author** (build a file): `cljgen` (Clojure, EDN data → `.clj`) or the `sexpsplice append` loop — add one form at a time.
- **Edit** (change an existing file): `sexpsplice` by form index — name a form, supply one replacement, everything else is preserved **byte-for-byte** (comments, reader macros `#()`/`#{}`, formatting all survive).

Never hand-edit Clojure with sed, python string munging, or `pr-str` — those corrupt delimiters, expand reader macros into `(fn* ...)`, and drop comments. **This is a standing user rule (2026-09-28): a broken `.clj` file is either reverted to a prior good state or rewritten from the ground up with sexpsplice — never incrementally hand-repaired.**

## Enforcement: `clj_guard` — the rule is now a gate, not a suggestion

This skill was not enough on its own: an agent can hold the rule and still reach for `sed` in a long session, because nothing *stopped* it. So the rule is now **enforced** by `clj_guard`, a Hermes `pre_tool_call` shell hook installed at `~/.hermes/agent-hooks/clj_guard.py`.

**If you try to rewrite a `.clj`/`.cljc`/`.cljs`/`.edn` file as text, the call is BLOCKED** — `sed -i`/`perl -i`/`awk -i inplace`, a scripting interpreter (`python3 -c "open('x.clj','w')…"`, `node -e`, `ruby -e`), a shell redirect carrying content (`echo '(ns x)' > f.clj`, `cat > f.clj <<EOF`), `tee`/`dd`/`truncate`, an interactive editor, or the **`patch`**/**`write_file`** tools on a Clojure path. The block message names the exact sexpsplice/cljgen command to use instead. **That message is the instruction.** Rewording the same `sed`, base64-ing it, hiding it in a helper script, or routing it through `execute_code` is not a fix — it is the exact failure this gate exists to catch. If the block is genuinely wrong for a legitimate workflow, that is a *bug in the guard*: add the case to the `ALLOW` table in `agent-hooks/test_clj_guard.py` and re-run `./install.sh`.

What still works, by design: everything `sexpsplice` (`list`/`get`/`set`/`append`/`delete`/`apply`/`find`/`move`/`insert`), anything invoking `cljgen` (including `clojure -M -m cljgen.cli`, since cljgen *is* Clojure), starting a file with `: > f.clj`, reads (`cat`/`grep`/`wc`/`sed -n`), `clj-kondo --lint`, `clojure -M`, and any non-Clojure file.

A second hook, **`pre_verify`**, fires once when a turn changed a `.clj` file and will not let you finish without the verification checklist: `clj-kondo --lint` + `sexpsplice list` + `wc -l` (≤ 50) + a real `~/.local/bin/clojure -M -e "(require '<ns>)"`.

Source, tests, installer: `agent-hooks/` inside the repo (resolve the root with `clj-repo-root`) — `python3 agent-hooks/test_clj_guard.py` (52 cases + wire protocol).

## When to Use

- **Authoring**: an LLM (or human) needs to *create* a Clojure file from scratch — use cljgen, or the `sexpsplice append` loop (one form at a time, review each).
- **Editing**: an LLM needs to change one form in an existing file without retyping the whole file (which corrupts delimiters/formatting).
- **Debugging a broken file**: stop editing; revert (`<file>.bak`, git) or rewrite via the append loop.
- You want delimiters guaranteed balanced by construction (the parser emits them).
- You need comment/reader-macro preservation — where `pr-str` re-serialization fails.
- You find yourself about to use sed/python/pr-str on a `.clj` file — stop, and use this instead.
- **On every Clojure turn, re-anchor the Standing rules below.** In long sessions these get dropped silently; the section is repeated deliberately for that reason.

## File-size rule (standing, compiler-enforced)

**Every `.clj` file must be at most 50 lines** (user directive, 2026-09, enforced by the user's compiler). Run `wc -l` after EVERY form you append; when a file nears the limit, split it into a new file by responsibility (one `defn` cluster per file) rather than cramming. A >50-line file is a broken artifact here, not a style nit. The verification checklist below has a matching `wc -l` check.

## Standing rules (re-assert on every Clojure turn — user directives, 2026-09-30)

These re-apply on EVERY Clojure turn; in long sessions they get dropped silently, so the skill states them redundantly:

1. **Structural editing only, via sexpsplice.** Never hand-text-patch a `.clj` (no sed, no python string munging, no pr-str, no hand-typed form bodies from memory). Author with cljgen or the sexpsplice append loop; edit by form index with `set`/`insert`. A broken file is reverted or rewritten from the ground up — never incrementally hand-repaired.
2. **Idiomatic, pure-functional style.** Pure functions of the data; immutable data structures (`update`, `assoc`, `dissoc`, `conj` — never mutation or `reduce` over the same collection while writing it). Thread state with `->` / `->>` wherever a pipeline fits; `doseq`/`for` for sequence work; `let` for local names.
3. **Verify ALL closing parentheses with tools, strictly.** The only valid verifiers are a real reader — `clj-kondo --lint`, the JVM (`clojure -M` load of the namespace), or sexpsplice's own reader (a successful `append`/`set` parses the form) — plus `wc -l` for the 50-line rule. **Never** by hand-counting, and **never** by a raw `str.count("(")`/`str.count(")")` in python/shell: docstrings and string literals routinely contain unbalanced `(`, so raw counts disagree with the reader (a form can be raw-count-balanced yet mis-nested, and raw-count-unbalanced yet valid). When kondo and the JVM disagree with your mental model, the tool wins, always.
4. **File-size rule:** every touched `.clj` ≤ 50 lines (`wc -l` after every form); split by responsibility when near the limit.

**Pitfall (2026-09-30, cost an entire session): `clojure.core/run!` is LAZY.** `(run! (map println) coll)` composes the transducer and returns the result WITHOUT forcing it, so the println side effects never fire and the output is silently empty. Force with `dorun`/`doall`. Also never name your own function `run!` — it shadows `clojure.core/run!` in that namespace and quietly rewires every `run! (map println ...)` call inside it.

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

**Pitfall (observed 2026-09-28): the closing tail of a deep form is where the
model's paren bookkeeping breaks.** If `sexpsplice append` says `no readable
form on stdin`, check the tail with a parser (clj-kondo on the single-form
file), fix it, and re-verify with BOTH clj-kondo AND a successful sexpsplice
append (two independent parsers). `clj-paren-repair` can fix an isolated
unbalanced form, but only ever on a scratch copy — never trust its output
without the lint+reader re-verify.

**Pitfall: `patch`/`write_file` mangle paren-heavy .clj content** (dropped
closers, escape drift). After any such write on a .clj file: clj-kondo
IMMEDIATELY — and if it fails, treat the file as broken (revert/rewrite per
the rule above); do NOT keep patching.

## Locating code (resolve it — never hardcode a home path)

**Syncthing is canonical for all repositories and projects.** The shared folder holds
`repos/` (git repositories) and `projects/` (non-repo projects such as `cljgen`,
`sexpsplice`), flat at its root alongside `backups/`. Find it by **discovery**, not by
assuming a path — a Syncthing folder root is any directory containing a `.stfolder` marker:

```bash
REPO="$(clj-repo-root)"      # the clojure-llm-tools checkout
ROOT="$(repos-root)"         # canonical repos root — every repository lives here
PROJ="$(projects-root)"      # canonical projects root
repo-root postbox            # any repo by name, e.g. <repos-root>/postbox
repo-root --list             # show what resolved, for debugging
```

`repo-root` ships at `scripts/repo-root` (installed on PATH alongside `clj-repo-root`,
`repos-root` and `projects-root`). Overrides for other hosts: `$REPOS_ROOT`,
`$PROJECTS_ROOT`, and legacy `$CLJ_TOOLS_ROOT`. It **never guesses** — a wrong path is worse
than a clear failure, because an agent will cheerfully use it.

**Caveat: two sync roots.** A host can turn up a SECOND `.stfolder` dir (on this host,
the live shared folder plus a stale mirror at `~/.openclaw/workspace`). Until 2f932dc,
first-match discovery silently returned the stale root; the ranked, search-every-root
behaviour now handles it. If `--list` ever shows a surprising winner, read the candidate
table instead of overriding blindly, and use `REPOS_ROOT`/`PROJECTS_ROOT` for a
one-off override.

**The git remote is the source of truth for any repo, not the directory it sits in.**
For this one: `github-rk:dbelavy/clojure-llm-tools.git`.

**One remote, and it is GitHub.** `origin` is the only remote; adding a second one is how this
repo grew a divergent "second checkout" and the path churn that came with it. Don't.

Use `"$REPO/..."` / `"$(repos-root)/<name>"` in commands rather than any literal home path.

## The tool

- **`sexpsplice`** — launcher at `~/bin/sexpsplice`; source `sexpsplice/` inside the repo
  (resolve the root as above). The launcher discovers its project directory the same way
  (`$SEXPSPLICE_HOME` overrides), so it follows the repo if the layout moves.
- **`cljgen`** — the emit-side companion. **Clojure** (`cljgen-clj/`, EDN in → balanced `.clj` out; `clj-kondo`-gated, byte-exact against the Python reference): `clojure -M -m cljgen.cli forms.edn out.clj`. The Python reference `cljgen/cljgen.py` (module, imported — not a CLI) is kept only to byte-verify the Clojure port — **author with the Clojure `cljgen`, not the Python module.** Use cljgen to *create* files; use sexpsplice to *edit* them.

**cljgen EDN mapping — the one trap to internalise.** Because EDN has no list literal, you author each target form as an **EDN vector** and `to-form` rewrites it to a **list** in the output. Vectors (arg/binding vectors) are forced with the `{:__vec__ [...]}` escape map — a bare multi-element vector would be converted to a list and produce invalid Clojure. Concretely:

- **Forms are lists.** Author the whole form as an EDN vector; `to-form` turns it into a list. `(defn add [a b] (+ a b))` is authored as `(defn add {:__vec__ [a b]} (+ a b))` → emits `(defn add [a b] (+ a b))`.
- **Arg/binding vectors use `{:__vec__ [...]}`.** `(let {:__vec__ [a 1 b 2]} (+ a b))` → `(let [a 1 b 2] (+ a b))`. Nested vectors work too: `(let {:__vec__ [a 1 b {:__vec__ [2 3]}]} …)` → `(let [a 1 b [2 3]] …)`. A single-arg vector may also be written bare as `[n]` (the 1-element-symbol exception keeps it a vector), so `(defn square [n] …)` works as-is — but `{:__vec__ [n]}` is the unambiguous form.
- **Never author a bare multi-element vector for a binding/arg vector.** `to-form` converts it to a list → `(let (a 1 b 2) …)` / `(defn add (a b) …)` (both invalid Clojure). Always `{:__vec__ […]}`.
- **`(atom nil)` is a LIST call, not a vector.** Author it so the head is the symbol `atom`; `to-form` emits the list `(atom nil)`, correctly distinct from a vector.
- **Reader macros / raw text / char literals go through the escape maps, never a plain string:** `{:__raw__ "#(+ % 1) xs"}` → verbatim `#(+ % 1) xs` (balance-checked); `{:__char__ "newline"}` → `\newline` (a char literal); `{:__vec__ […]}` → a vector `[ … ]`. A plain string always becomes a quoted Clojure string.

The whole output is balance-checked before the write. (The old Python mapping `list`→`(` / `tuple`→`[` / `Sym`/`Kw`/`Raw` is retired for authoring — it remains only as the byte-reference the port is verified against.)

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
- **`move` canonicalises inter-form separators.** It collapses blank lines *between* top-level forms to single newlines (the block model drops whitespace and re-emits with single-newline separators). A form's *own* internal content — including blank lines inside it — is preserved byte-for-byte. So `(def b\n\n  2)` keeps its internal blank line, but the gap between `(def a 1)` and `(def b ...)` does not survive a `move`. If you need whitespace exactly preserved, use `set` (byte-preserving), not `move`.
- **`insert` at the same index stacks in REVERSE.** Each `insert` places its form *at* index N and pushes existing forms down, so three `insert idx 0` calls land as C, B, A (reverse of insertion order). To insert several forms in forward order at the front, insert them in reverse, or `append` then `move` (chained moves fix ordering).

**Path syntax** = vector of selectors, each descending one level:
- integer → Nth value child (0-based, whitespace/comments skipped)
- keyword → map value at key `:k`
Examples: `[2]` = top-level form 2; `[1 3]` = form 1's 3rd child (a defn body); `[3 2 :port]` = form 3 → its 2nd child (a map) → value at `:port`. A bare integer is shorthand for `[n]`.

**apply** (stdin, EDN vector): `[{:op :set :path [2] :form "(def beta 43)"} {:op :append :form "(def d 1)"} {:op :delete :path [3]}]`. All ops apply atomically — any error → no write, exit 1.

Full CRUD + batch + discover/reorder: create (append/insert), read (list + get + find), update (set), delete (delete), transactional multi-edit (apply), reorder (move).

**The spec** lives at `<repo>/sexpsplice/SPEC.md` (resolve `<repo>` with `clj-repo-root`) (commands, path syntax, invariants, acceptance criteria, non-goals). Read it before extending.

stdin carries exactly one form. Errors exit 1 with `no readable form on stdin`, `index <i> out of range 0-<N-1>`, or `cannot parse file <file>` (the last one = the file is broken: revert or rewrite, don't patch).

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
- [ ] `insert` at 0/mid/end (and in an empty file) produces clean single-newline separation
- [ ] `--dry-run` prints the would-be result and leaves the file untouched; `--no-backup` suppresses the `.bak` backup; a real write creates `<file>.bak`
- [ ] every touched file is at most 50 lines (`wc -l`); split into new files by responsibility if not
- [ ] `clj-kondo --lint` = 0 errors (disable `:namespace-name-mismatch` for test namespaces)
- [ ] after any `set`/`insert`/rewrite: the JVM actually loads the namespace (`~/.local/bin/clojure -M -e "(require '<ns>)"`) and the test suite passes — kondo alone is not proof the form compiles/behaves
- [ ] side-effect pipelines use `dorun`/`doall`, not `run!` (lazy); no own function named `run!`

## Environment notes (this host)

- Foreground `clojure` = `/usr/bin/clojure` (plain 1.12 jar, no tools.deps: `-M:alias` fails with "No such file or directory"). Background and `~/.local/bin/clojure` = tools.deps (works). Use `~/.local/bin/clojure` explicitly.
- `clj-kondo` usage on this version: `clj-kondo --lint <file>` (positional `clj-kondo <file>` prints usage).
- `execute_code`/heredocs truncate long Python containing parens/quotes — build files via short `python3 - <<'PYEOF'` snippets or write_file, then clj-kondo.
- cljgen v3 status (2026-09-28): gaps 1-3 CLOSED — Raw reader-macros, Char literals + proper bal_ok char grammar, indent-aware pretty printer. Remaining: data-reader direction (read .clj -> Python data) not yet built.

## Setup notes

- Project: `sexpsplice/` inside the repo checkout with `deps.edn` (resolve the root with `clj-repo-root`); `~/bin/sexpsplice` discovers its project directory the same way via `projects-root` (`$SEXPSPLICE_HOME` overrides).
- Launcher `~/bin/sexpsplice` runs `clojure -Srepro -Sdeps '<deps>' -M sexpsplice.clj "$@"`; `SEXPSPLICE_HOME` overrides the project dir.
- clj-kondo install: `curl -sL https://github.com/clj-kondo/clj-kondo/releases/download/v<VER>/clj-kondo-<VER>-linux-amd64.zip` (asset name has NO `v` prefix — `clj-kondo-2026.08.04-linux-amd64.zip`, not `.../latest/download/...`).
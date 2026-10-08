# sexpsplice — implementation gotchas (preserve these)

Maintenance-level notes for anyone extending `sexpsplice.clj`. These were
originally in the clojure skill but were dropped when David renamed the skill
`clojure-structural-editing` → `clojure-programming` (v1.3.0). The usage skill
is deliberately lean now; this file carries the hard-won implementation detail
so it is not lost. Read the source (`sexpsplice/sexpsplice.clj`) alongside.

1. **Reader idiom**: 2-arg `(read r :eof)` throws ClassCastException (Keyword →
   PushbackReader). The 2-arg form's second arg is a *read-at position*, not an
   eof sentinel. Correct: `(read {:eof ::eof} r)` — pass an opts **map** with
   `:eof`.

2. **Top-level child layout is NOT even/odd.** `p/parse-string-all` returns a
   `FormsNode` whose children interleave forms, whitespace, and comments, and a
   `CommentNode` **absorbs its trailing newline** (the next form immediately
   follows the comment node — no separate newline node). Index forms by scanning
   for children that are neither `n/whitespace?` nor `n/comment?`.

3. **Append separator**: strip trailing whitespace nodes first, then `conj`
   `(n/newlines 1) new-node (n/newlines 1)` so you fully control the separator
   and trailing newline.

4. **Delete uses plain `z/remove`, not `z/remove-preserve-newline`.**
   `remove-preserve-newline` keeps the newline (for nested edits), which leaves
   a blank line at top level. Plain `z/remove` strips the node + trailing
   newline — clean for top-level forms.

5. **Navigation: UNSTARRED `z/down`/`z/right` skip whitespace+comments;
   STARRED `z/down*`/`z/right*` are raw moves that land ON whitespace.** For
   path navigation always use unstarred. (Opposite of what the names suggest.)

6. **`z/root` returns a NODE, not a loc — `z/up` returns a loc.** To get back to
   the root *loc* after an edit (needed when chaining batch ops), walk `z/up`
   to the top (`to-root`), don't use `z/root`.

7. **Batch `apply` must resolve each op against the ROOT, not the previous op's
   result loc.** After `z/replace`/`z/remove` the loc is positioned at the
   edited node; the next op's path would resolve relative to that node. Wrap
   each op's result in `to-root`.

8. **Comments are never deleted** — `delete` removes only the form + a newline;
   an orphaned comment is left in place for deliberate cleanup.

9. **rewrite-clj is on Clojars, not Maven Central**, and version `1.3.8` does
   not exist — pin `1.2.57`. `deps.edn` needs an explicit `clojars` repo
   (`:mvn/repos {"clojars" {:url "https://repo.clojars.org/"}}`).

10. **babashka SCI breaks `read`/`clojure.tools.reader`/`edamame`** on some
    hosts. Use plain `clojure -M`, not `bb`, for reader correctness.

11. **Java NIO varargs**: `Files/exists`, `Files/write`, and
    `Files/createTempFile` have NO no-varargs overload in Clojure — always pass
    the trailing array:
    - `(Files/write tmp bytes (into-array java.nio.file.OpenOption []))`
    - `(Files/exists src (into-array java.nio.file.LinkOption []))`
    - `(Files/createTempFile dir ".pre-" ".suf" (into-array java.nio.file.attribute.FileAttribute []))`
    Compilation fails at runtime with "No matching method ... taking N args"
    otherwise.

12. **Atomic write = temp file in same dir + `Files/move` with `ATOMIC_MOVE`
    (fallback to `REPLACE_EXISTING`)**, and backup to `<file>.bak` first. Use the
    fallback because ATOMIC_MOVE throws on some filesystems. Do NOT `spit`
    directly.

13. **`move`/`insert` use a block model, not the zipper**: `form-blocks` splits
    top-level children into `[leading-comments..., form]` blocks (comments attach
    to the FOLLOWING form — doc convention), drops whitespace, and `emit-string`
    re-renders with single-newline separators. This is deliberately
    canonicalizing (unlike `set`/`delete`/`append` which preserve bytes). This is
    why `move` collapses inter-form blank lines (a form's *internal* blank lines
    survive; only separators between forms canonicalise) and why repeated
    `insert` at the same index stacks in reverse.

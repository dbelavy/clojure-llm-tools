#!/usr/bin/env python3
"""clj_guard — enforce structural (syntax-tree) editing of Clojure in Hermes.

Why this exists
---------------
A skill is advice; the model can ignore it. This is a *gate*. It sits on Hermes's
``pre_tool_call`` hook and BLOCKS the specific moves that corrupt Clojure source —
``sed``/``perl -i``/``awk``, a scripting interpreter writing the file, a shell
redirect with content, ``tee``/``dd``, an interactive editor, or the ``patch``/
``write_file`` tools — whenever the target is a ``.clj``/``.cljc``/``.cljs``/``.edn``
file. The block message teaches the correct move (sexpsplice by form index / cljgen)
at the exact moment the model reaches for the wrong one. That timing is the whole
point: guidance delivered at the moment of the mistake is what actually changes
behaviour, in a way that a skill loaded (or not) at session start does not.

It also nudges at ``pre_verify`` so a turn that touched Clojure cannot finish without
a reader-verified check, and can optionally inject a one-line reminder per turn.

Hooks implemented (see Hermes docs: user-guide/features/hooks.md)
-----------------------------------------------------------------
``pre_tool_call``  BLOCK raw-text mutation of a Clojure file.
``pre_verify``     one-shot nudge to verify structurally before finishing.
``pre_llm_call``   optional short standing reminder in a Clojure workspace.

Wire protocol (Hermes ``agent/shell_hooks.py``)
-----------------------------------------------
stdin  JSON: {hook_event_name, tool_name, tool_input, session_id, cwd, profile, extra}
stdout JSON: {"action":"block","message":...} | {"action":"continue","message":...}
             | {"context":...} | nothing at all for a no-op.

Design notes
------------
* **stdlib only** — runs under any ``python3`` on the host, no venv, no imports
  from the Hermes tree (a hook that needs the tree breaks on upgrade).
* **never crashes** — any internal error exits 0 having printed nothing. The
  default (fail-open) then lets the tool through. A steering guard that wedges
  every tool call on a bug is far worse than one that occasionally misses; set
  ``fail_closed: true`` in the config entry if you want the opposite trade.
* **allows the documented workflow** — a bare truncation (``: > f.clj``), reads
  (``cat``/``grep``/``wc``), and anything invoking ``sexpsplice``/``cljgen`` pass.
"""

from __future__ import annotations

import json
import os
import re
import sys

__version__ = "1.0.0"

# ---------------------------------------------------------------- file types

CLJ_EXTS = (".clj", ".cljc", ".cljs", ".edn", ".bb")

_EXT_ALT = r"(?:clj|cljc|cljs|edn|bb)"
# A path-ish token ending in a Clojure extension, as it appears inside a shell line.
_CLJ_PATH = r"[\w./~+@-]*[\w./~+@-]+\.%s\b" % _EXT_ALT
_CLJ_PATH_RE = re.compile(_CLJ_PATH, re.I)

# Tools whose entire purpose is writing a file's bytes.
_FILE_TOOLS = frozenset({"patch", "write_file", "edit_file", "create_file"})
# Script-execution tools: block only when they name a Clojure file.
_CODE_TOOLS = frozenset({"execute_code", "code_interpreter", "run_code"})

# If any of these appear, a real structural tool is in play — stand down.
# (Cljgen is Python, so this also keeps `python3 .../cljgen.py` legal.)
_APPROVED = ("sexpsplice", "cljgen")

# ------------------------------------------------------- shell-command rules

# In-place stream editors: these rewrite the file bytes in place.
_INPLACE_EDITORS = (
    (re.compile(r"\bsed\b[^|;&]*?(?:\s-i\b|\s-i\.|\s--in-place\b)"), "in-place `sed -i`"),
    (re.compile(r"\bperl\b[^|;&]*?(?:\s-i\b|\s-i\.|\s--in-place\b)"), "in-place `perl -i`"),
    (re.compile(r"\bawk\b[^|;&]*?\s-i\s+inplace\b"), "in-place `awk -i inplace`"),
)

# A scripting interpreter that can open()/write() the file itself. Matched
# anywhere in the line on purpose: `sudo python3 ...` and `command python3 ...`
# must be caught, and the "does it mention a Clojure file" precondition plus the
# sexpsplice/cljgen allowlist keep this from over-firing.
_INTERPRETERS = re.compile(
    r"\b(?:python3?(?:\.\d+)?|pypy3?|ruby|node|deno|bun|php|lua|"
    r"Rscript|julia|groovy|tclsh|osascript)\b"
)

# Whole-file rewrite helpers.
_REWRITERS = re.compile(r"\b(?:tee|sponge|dd|truncate|csplit)\b")
# Interactive editors (a pty is not how an agent should touch a syntax tree).
_INTERACTIVE = re.compile(r"(?:^|[|;&(]\s*)(?:ed|ex|vi|vim|nvim|nano|emacs|pico|micro)\b")

# `> file.clj` / `>> file.clj` / `&> file.clj` (but NOT `2>` / `1>`, which are fd
# plumbing on a stream that is not the file's content).
_REDIRECT_RE = re.compile(r"(?<![0-9])&?>>?\s*(?P<path>%s)" % _CLJ_PATH, re.I)
# Producers that are a pure truncation, not a content write.
_TRUNCATION_ONLY = {"", ":", "true", "printf ''", 'printf ""', "printf ''", ":\n"}

# An editor/scripting tool the model might reach for directly.
_EDIT_HINT = (
    "sed/perl/awk, a scripting interpreter, a shell redirect with content, "
    "tee/dd, an interactive editor, or the patch/write_file tools"
)


def is_clj_path(value: object) -> bool:
    """True for a path string naming a Clojure/EDN file."""
    if not isinstance(value, str):
        return False
    return value.lower().split("?")[0].endswith(CLJ_EXTS)


def clj_paths_in(text: str) -> list[str]:
    """Every Clojure-looking path token mentioned in *text*."""
    if not isinstance(text, str):
        return []
    return _CLJ_PATH_RE.findall(text)


def _segment_before(cmd: str, index: int) -> str:
    """The last shell 'word group' before *index* — what feeds the redirect."""
    head = cmd[:index]
    for sep in ("\n", ";", "&&", "||", "|"):
        head = head.rsplit(sep, 1)[-1]
    return head.strip()


def terminal_verdict(command: str) -> str | None:
    """Return a reason string to BLOCK *command*, or None to allow it."""
    if not isinstance(command, str) or not command.strip():
        return None

    # Nothing Clojure about this command — not our business.
    if not clj_paths_in(command):
        return None

    # A sanctioned structural tool is in the pipeline; let it run.
    if any(tok in command for tok in _APPROVED):
        return None

    for pattern, label in _INPLACE_EDITORS:
        if pattern.search(command):
            return label

    if _INTERPRETERS.search(command):
        return "a scripting interpreter"

    # Content written into a Clojure file via a redirect.
    for match in _REDIRECT_RE.finditer(command):
        producer = _segment_before(command, match.start())
        if producer in _TRUNCATION_ONLY:
            continue  # `: > f.clj` — the documented way to start an empty file
        return "a shell redirect writing file content"

    if _REWRITERS.search(command):
        return "tee/dd/truncate"

    if _INTERACTIVE.search(command):
        return "an interactive editor"

    return None


# ------------------------------------------------------------- block messages

def _steer_block(what: str, target: str = "") -> str:
    # NOTE: built by concatenation, never str.format()/f-string on a template —
    # this message deliberately contains literal `#()` and `#{}`, which .format()
    # would try to read as replacement fields.
    where = ("\n  target: " + target) if target else ""
    return (
        "BLOCKED by clj_guard: " + what + " cannot rewrite Clojure source." + where + "\n"
        "\n"
        "Clojure must be edited STRUCTURALLY — as a syntax tree, addressed by form\n"
        "index — never as text. Text editing corrupts delimiters, expands reader\n"
        "macros (#() and #{} become (fn* ...)), and silently drops comments; a raw\n"
        "paren count also lies, because docstrings and string literals contain parens.\n"
        "\n"
        "Do this instead:\n"
        "  sexpsplice list   <file>            # top-level forms, with indices\n"
        "  sexpsplice find   <file> <substr>   # locate the form you mean\n"
        "  sexpsplice get    <file> <path>     # print the full form, untruncated\n"
        "  sexpsplice set    <file> <path>     # ONE replacement form on stdin\n"
        "  sexpsplice delete <file> <path>     # remove the form at path\n"
        "  sexpsplice insert <file> <idx>      # ONE form on stdin at index <idx>\n"
        "  sexpsplice move   <file> <from> <to>  # move a top-level form\n"
        "  echo '(defn f [x] (* x x))' | sexpsplice append <file>\n"
        "  sexpsplice apply  <file>            # batch, atomic: EDN vector on stdin\n"
        "Create a new file with cljgen (data -> .clj), or the append loop one form\n"
        "at a time. Path syntax: [2] = 3rd top-level form, [1 3] = form 1's 3rd child,\n"
        "[3 2 :port] = form 3 -> child 2 (a map) -> :port.\n"
        "\n"
        "Then verify (all three, every time):\n"
        "  clj-kondo --lint <file> && sexpsplice list <file> && wc -l <file>\n"
        "A bare truncation (': > file.clj'), reads (cat/grep/wc), and any command\n"
        "using sexpsplice or cljgen are allowed."
    )


def _verify_nudge(changed: list[str]) -> str:
    files = " ".join(changed) if changed else "<file>"
    return (
        "Structural verification is required before you finish (this nudge fires "
        "once). Files changed: {files}\n"
        "\n"
        "For each .clj/.edn file you touched, run and report:\n"
        "  1. clj-kondo --lint {files}                     # 0 errors\n"
        "  2. sexpsplice list {files}                       # re-parses the whole file\n"
        "  3. wc -l {files}                                 # every file <= 50 lines\n"
        "  4. ~/.local/bin/clojure -M -e \"(require '<ns>)\"  # the JVM really loads it\n"
        "\n"
        "clj-kondo passing is NOT proof the form compiles or behaves; step 4 is.\n"
        "If sexpsplice reports 'cannot parse file', the file is broken: revert it\n"
        "(<file>.bak or git) or rewrite it via the append loop — never hand-repair\n"
        "it incrementally, and never reach for sed/python to patch the tail."
    ).format(files=files)


# ------------------------------------------------------- pre_llm_call reminder

_REMINDER = (
    "[clj_guard] This workspace contains Clojure. Edit .clj/.edn structurally only: "
    "sexpsplice by form index to change a form, cljgen to create a file, or the "
    "append loop one form at a time. Never sed/python/patch/pr-str a .clj file — "
    "raw text edits corrupt delimiters and drop comments. Verify with "
    "clj-kondo --lint + sexpsplice list + wc -l (<=50 lines/file)."
)


def _workspace_has_clojure(cwd: str, *, max_entries: int = 400) -> bool:
    """Cheap bounded scan of *cwd* (and one level down) for Clojure files."""
    if not cwd or not os.path.isdir(cwd):
        return False
    seen = 0
    try:
        with os.scandir(cwd) as it:
            for entry in it:
                seen += 1
                if seen > max_entries:
                    return False
                try:
                    if entry.is_file() and entry.name.lower().endswith(CLJ_EXTS):
                        return True
                    if entry.is_dir() and not entry.name.startswith("."):
                        with os.scandir(entry.path) as sub:
                            for s in sub:
                                seen += 1
                                if seen > max_entries:
                                    return False
                                if s.name.lower().endswith(CLJ_EXTS):
                                    return True
                except OSError:
                    continue
    except OSError:
        return False
    return False


# ------------------------------------------------------------------ dispatch

def _tool_args(payload: dict) -> dict:
    args = payload.get("tool_input")
    return args if isinstance(args, dict) else {}


def _path_arg(args: dict) -> str:
    for key in ("path", "file_path", "filename", "file"):
        val = args.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def handle_pre_tool_call(payload: dict) -> dict | None:
    tool = payload.get("tool_name") or ""
    args = _tool_args(payload)

    if tool in _FILE_TOOLS:
        target = _path_arg(args)
        if is_clj_path(target):
            return {
                "action": "block",
                "message": _steer_block(
                    "the `%s` tool (a raw byte writer)" % tool, target
                ),
            }
        return None

    if tool == "terminal":
        command = args.get("command") or ""
        reason = terminal_verdict(command)
        if reason:
            return {
                "action": "block",
                "message": _steer_block(reason) + "\n\n  offending command: %s" % command.strip()[:400],
            }
        return None

    if tool in _CODE_TOOLS:
        code = args.get("code") or args.get("script") or ""
        if isinstance(code, str) and clj_paths_in(code):
            return {
                "action": "block",
                "message": _steer_block("a scripted file write", clj_paths_in(code)[0]),
            }
        return None

    return None


def handle_pre_verify(payload: dict) -> dict | None:
    extra = payload.get("extra")
    if not isinstance(extra, dict):
        return None
    # One-shot: `attempt` is 0 on the first pass, then counts prior nudges.
    try:
        attempt = int(extra.get("attempt") or 0)
    except (TypeError, ValueError):
        attempt = 0
    if attempt:
        return None
    changed = extra.get("changed_paths")
    if not isinstance(changed, list):
        return None
    clj = [p for p in changed if is_clj_path(p)]
    if not clj:
        return None
    return {"action": "continue", "message": _verify_nudge(clj)}


def handle_pre_llm_call(payload: dict) -> dict | None:
    cwd = payload.get("cwd") or ""
    if _workspace_has_clojure(cwd):
        return {"context": _REMINDER}
    return None


_HANDLERS = {
    "pre_tool_call": handle_pre_tool_call,
    "pre_verify": handle_pre_verify,
    "pre_llm_call": handle_pre_llm_call,
}


def evaluate(payload: dict) -> dict | None:
    """Pure dispatch — separated from I/O so it is directly unit-testable."""
    handler = _HANDLERS.get(str(payload.get("hook_event_name") or ""))
    if handler is None:
        return None
    return handler(payload)


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            return 0
        verdict = evaluate(payload)
        if verdict:
            sys.stdout.write(json.dumps(verdict))
    except Exception:  # never wedge the agent — fall open, exit clean
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

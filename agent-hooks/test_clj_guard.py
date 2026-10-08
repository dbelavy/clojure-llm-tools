#!/usr/bin/env python3
"""Tests for clj_guard — the Clojure structural-editing gate.

Run:  python3 agent-hooks/test_clj_guard.py

Two layers:
  1. ``evaluate()`` unit cases — the verdict for a given payload.
  2. One end-to-end subprocess run — the real Hermes wire protocol
     (JSON on stdin -> JSON on stdout), so a change to the I/O shape is caught.

The BLOCK table is the contract: every entry is a command that would corrupt a
Clojure file if it ran. The ALLOW table is the inverse contract — the documented
sexpsplice/cljgen workflow and ordinary read-only work MUST keep working, or the
guard becomes the thing agents route around.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clj_guard as g  # noqa: E402

HERE = Path(__file__).resolve().parent
GUARD = HERE / "clj_guard.py"

# ---- commands that MUST be blocked (each would rewrite .clj/.edn as text) ----
BLOCK_COMMANDS = [
    "sed -i 's/foo/bar/' core.clj",
    "sed --in-place 's/a/b/' core.clj",
    "sed -i.bak 's/a/b/' core.clj",
    "perl -i -pe 's/a/b/' core.clj",
    "awk -i inplace '{print}' core.clj",
    "python3 -c \"open('core.clj','w').write('(ns x)')\"",
    "python3 rewrite.py core.clj",
    "ruby -e 'File.write(\"core.clj\", \"x\")'",
    "node -e 'fs.writeFileSync(\"core.clj\",\"x\")'",
    "echo '(ns demo.core)' > core.clj",
    "printf '(def a 1)' >> core.clj",
    "cat > core.clj <<'EOF'",
    "cat /tmp/payload >> core.clj",
    "tee core.clj < /tmp/x",
    "dd if=/dev/zero of=core.clj bs=1 count=10",
    "truncate -s 0 core.clj",
    "vim core.clj",
    "nvim core.clj",
    "sed -i 's/1/2/' project/deps.edn",
    "python3 -c \"import pathlib;pathlib.Path('x.edn').write_text('{}')\"",
]

# ---- commands that MUST be allowed (the sanctioned workflow + reads) ----
ALLOW_COMMANDS = [
    "sexpsplice list core.clj",
    "sexpsplice get core.clj '[1 3]'",
    "echo '(ns demo.core)' | sexpsplice append core.clj",
    "echo '(defn f [x] (* x x))' | sexpsplice append core.clj",
    "printf '(def b 2)' | sexpsplice insert core.clj 1",
    "sexpsplice apply core.clj <<'EOF'",
    "sexpsplice find core.clj defn",
    ": > core.clj",                       # documented way to start an empty file
    "true > core.clj",
    "clj-kondo --lint core.clj",
    "clj-kondo --lint src/core.clj project/deps.edn",
    "cat core.clj",
    "grep -n defn core.clj",
    "wc -l core.clj",
    "head -20 core.clj",
    "sed -n '1,10p' core.clj",            # read-only sed (no -i)
    "git diff core.clj",
    "git checkout -- core.clj",
    "clojure -M -e \"(require 'demo.core)\"",
    "~/.local/bin/clojure -M -e \"(require 'demo.core)\"",
    "python3 /home/david/repos/clojure-llm-tools/cljgen/cljgen.py --out core.clj",
    "ls -la",
    "git status",
    "python3 agent-hooks/test_clj_guard.py",   # touches no Clojure file
]

# ---- file-writing tools ----
BLOCK_FILE_TOOLS = [
    ("patch", {"path": "core.clj"}),
    ("patch", {"path": "project/deps.edn"}),
    ("write_file", {"path": "src/app/core.cljc"}),
    ("write_file", {"file_path": "view.cljs"}),
]
ALLOW_FILE_TOOLS = [
    ("patch", {"path": "server.py"}),
    ("write_file", {"path": "README.md"}),
    ("write_file", {"path": "notes.txt"}),
    ("read_file", {"path": "core.clj"}),
]


def _tc(tool: str, args: dict) -> dict:
    return {"hook_event_name": "pre_tool_call", "tool_name": tool, "tool_input": args}


def _fails() -> list[str]:
    f: list[str] = []

    for cmd in BLOCK_COMMANDS:
        verdict = g.evaluate(_tc("terminal", {"command": cmd}))
        if not verdict or verdict.get("action") != "block":
            f.append(f"SHOULD BLOCK terminal: {cmd!r} -> {verdict!r}")

    for cmd in ALLOW_COMMANDS:
        verdict = g.evaluate(_tc("terminal", {"command": cmd}))
        if verdict is not None:
            f.append(f"SHOULD ALLOW terminal: {cmd!r} -> {verdict.get('message','')[:80]!r}")

    for tool, args in BLOCK_FILE_TOOLS:
        verdict = g.evaluate(_tc(tool, args))
        if not verdict or verdict.get("action") != "block":
            f.append(f"SHOULD BLOCK {tool} {args!r} -> {verdict!r}")

    for tool, args in ALLOW_FILE_TOOLS:
        verdict = g.evaluate(_tc(tool, args))
        if verdict is not None:
            f.append(f"SHOULD ALLOW {tool} {args!r} -> {verdict!r}")

    # block messages must actually teach the fix, not just say no
    msg = g.evaluate(_tc("terminal", {"command": "sed -i 's/a/b/' core.clj"}))["message"]
    for token in ("sexpsplice set", "sexpsplice append", "clj-kondo", "wc -l"):
        if token not in msg:
            f.append(f"block message missing guidance token {token!r}")

    # pre_verify: one-shot, Clojure-only
    pv = {"hook_event_name": "pre_verify", "extra": {"attempt": 0, "changed_paths": ["a.clj"]}}
    if (g.evaluate(pv) or {}).get("action") != "continue":
        f.append("pre_verify should nudge on first attempt with a .clj change")
    pv["extra"]["attempt"] = 1
    if g.evaluate(pv) is not None:
        f.append("pre_verify must be one-shot (attempt>0 -> no nudge)")
    pv_py = {"hook_event_name": "pre_verify", "extra": {"attempt": 0, "changed_paths": ["a.py"]}}
    if g.evaluate(pv_py) is not None:
        f.append("pre_verify must not nudge for non-Clojure changes")

    # unknown event / garbage payloads never raise, never emit
    for junk in ({"hook_event_name": "nope"}, {}, {"hook_event_name": "pre_tool_call"}):
        if g.evaluate(junk) is not None:
            f.append(f"unexpected verdict for {junk!r}")

    return f


def _e2e() -> list[str]:
    """Drive the real script the way Hermes does: JSON in on stdin."""
    failures: list[str] = []

    payload = {
        "hook_event_name": "pre_tool_call",
        "tool_name": "terminal",
        "tool_input": {"command": "sed -i 's/a/b/' core.clj"},
        "session_id": "sess_test",
        "cwd": "/tmp",
        "profile": "default",
        "extra": {},
    }
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload), capture_output=True, text=True, timeout=20,
    )
    if proc.returncode != 0:
        failures.append(f"e2e block run exited {proc.returncode}: {proc.stderr[:200]}")
    else:
        try:
            out = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError as exc:
            failures.append(f"e2e block run emitted non-JSON {proc.stdout[:200]!r} ({exc})")
        else:
            if out.get("action") != "block":
                failures.append(f"e2e block run returned {out!r}")

    # A no-op must emit NOTHING (empty stdout is the documented silent path).
    payload["tool_input"] = {"command": "sexpsplice list core.clj"}
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload), capture_output=True, text=True, timeout=20,
    )
    if proc.returncode != 0 or proc.stdout.strip():
        failures.append(f"e2e allow run should be silent, got {proc.returncode}/{proc.stdout[:200]!r}")

    # Malformed stdin must not crash or emit.
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input="not json at all", capture_output=True, text=True, timeout=20,
    )
    if proc.returncode != 0 or proc.stdout.strip():
        failures.append(f"malformed stdin should exit 0 silently, got {proc.returncode}/{proc.stdout[:200]!r}")

    return failures


def main() -> int:
    failures = _fails() + _e2e()
    total = len(BLOCK_COMMANDS) + len(ALLOW_COMMANDS) + len(BLOCK_FILE_TOOLS) + len(ALLOW_FILE_TOOLS)
    if failures:
        print(f"FAIL ({len(failures)} problems)\n")
        for f in failures:
            print("  -", f)
        return 1
    print(f"PASS — {total} cases + e2e wire protocol ({g.__version__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

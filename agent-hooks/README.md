# agent-hooks — making Hermes agents edit Clojure *structurally*

A skill is advice. An agent that has the skill can still reach for `sed` in a long
session, because nothing stops it. **`clj_guard` is the stop.**

It is a Hermes [`shell hook`](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks)
that sits on `pre_tool_call` and *blocks* the specific moves that corrupt Clojure
source, then hands back the correct move at the exact moment the agent reaches for
the wrong one. Guidance delivered at the moment of the mistake is what actually
changes behaviour — a rule loaded (or not) at session start is not.

## What it blocks

Any command or tool call that would rewrite a `.clj` / `.cljc` / `.cljs` / `.edn`
file as **text**:

- `sed -i`, `perl -i`, `awk -i inplace`
- a scripting interpreter — `python3 -c "open('x.clj','w')…"`, `node -e …`, `ruby -e …`
- a shell redirect **carrying content** — `echo '(ns x)' > core.clj`, `cat > core.clj <<EOF`
- `tee` / `dd` / `truncate` / `sponge`
- an interactive editor — `vim`, `nvim`, `emacs`, `nano`
- the **`patch`** and **`write_file`** tools, whenever the target is a Clojure file

## What it allows

The sanctioned workflow and ordinary reading must keep working, or the agent
routes around the gate:

- everything `sexpsplice` — `list`, `get`, `set`, `append`, `delete`, `apply`, `find`, `move`, `insert`
- anything invoking `cljgen` (including `python3 …/cljgen/cljgen.py`, since cljgen *is* Python)
- `: > core.clj` — the documented way to start an empty file (a bare truncation, no content)
- reads — `cat`, `grep`, `head`, `wc`, `sed -n '1,10p'`
- `clj-kondo --lint`, `clojure -M`, `git diff` / `git checkout`
- any file that is not Clojure

## Install

```bash
cd /path/to/clojure-llm-tools/agent-hooks
./install.sh                  # gate: pre_tool_call + pre_verify
./install.sh --with-reminder  # ...plus a one-line reminder each turn
./install.sh --dry-run        # show what would change
./install.sh --uninstall      # remove allowlist entries
```

Then **restart the gateway** so the hook registers:

```bash
systemctl --user restart hermes-gateway
```

## Three traps this installer exists to handle

**1. An unallowlisted hook is silently skipped.** Each `(event, command)` pair needs
consent. In a non-TTY context — gateway, cron, CI — there is no prompt, so a hook
that is configured but not allowlisted **does nothing and only logs a warning**. The
guard would look installed while you chatted with the agent over Telegram. So
`install.sh` writes `~/.hermes/shell-hooks-allowlist.json` for you:

```json
{"approvals": [{"event": "pre_tool_call", "command": "/home/david/.hermes/agent-hooks/clj_guard.py"}]}
```

The allowlist keys on the **exact command string, not the script hash** — so
re-installing over an edited script stays approved. `hermes hooks doctor` flags
mtime drift if you want to re-review an edit.

**2. `hermes hooks test --payload-file` speaks a different dialect than the runtime.**
The payload file must use **`args`** for the tool arguments (the internal
pre-serialization name). The real stdin payload uses **`tool_input`**. Feed it
`tool_input` and the hook sees an empty argument dict and silently stays quiet —
which looks exactly like a broken guard:

```bash
# correct — 'args' in the FILE, 'tool_input' on the WIRE
echo '{"tool_name":"terminal","args":{"command":"sed -i s/a/b/ core.clj"}}' > /tmp/p.json
hermes hooks test pre_tool_call --payload-file /tmp/p.json
#   parsed (Hermes wire shape): {"action": "block", "message": "BLOCKED by clj_guard: …"}
```

**3. `pre_verify` payload fields go at the TOP LEVEL of the payload file, not under `extra`.**
Same family as trap 2. The CLI's default payload for `pre_verify` carries `attempt` and
`changed_paths` as top-level keys, and it is the *runtime serializer* that routes them into
`extra` — which is where the hook reads them. Nest them under `extra` yourself and the hook
receives an empty `extra` and stays silent:

```bash
echo '{"attempt":0,"changed_paths":["src/core.clj"],"coding":true}' > /tmp/pv.json
hermes hooks test pre_verify --payload-file /tmp/pv.json   # -> {"action":"continue", …}
```

## Verify it is actually enforcing (not just configured)

Config state and enforcement are different things. The check that proves enforcement is to
**attempt the forbidden action against a scratch `.clj`** — if the gate is live the call is
refused; if it is not, you have only scribbled on throwaway data:

```bash
: > /tmp/guardtest.clj
echo '(ns guardtest.core)' | sexpsplice append /tmp/guardtest.clj
sed -i 's/a/b/' /tmp/guardtest.clj     # must be BLOCKED with the steer message
sexpsplice list /tmp/guardtest.clj     # the blocked write must NOT have landed
```

Confirm all three: the block *prevents* the write (file unchanged, not just warned), the
sanctioned `sexpsplice`/`cljgen` path still works, and `patch`/`write_file` on the same path
are refused too.

## Verify

```bash
python3 test_clj_guard.py     # 52 verdict cases + the stdin→stdout wire protocol
hermes hooks list             # configured + ✓ allowed
hermes hooks doctor           # exec bit, allowlist, mtime drift, JSON validity, timing
```

## Hook events

| Event | Action |
|-------|--------|
| `pre_tool_call` | Block a raw-text write to a Clojure file. Returns `{"action":"block","message":…}`. |
| `pre_verify` | One-shot nudge: a turn that touched `.clj` must verify before finishing (`clj-kondo --lint` + `sexpsplice list` + `wc -l` + a real `require`). |
| `pre_llm_call` | Optional. Injects a one-line reminder when the workspace contains Clojure files. |

## Extending it

Rules live in one place — add a `(compiled_regex, label)` to `_INPLACE_EDITORS` for
another in-place editor, or a regex to `_REWRITERS` / `_INTERPRETERS` for another
tool. Add a case to **both** tables in `test_clj_guard.py`: the `BLOCK` table is the
contract and the `ALLOW` table is the inverse contract that keeps the sanctioned
workflow alive. If a real workflow gets blocked, that is a bug — add it to `ALLOW`.

Design constraints, deliberate:

- **stdlib only** — no import from the Hermes tree, so it cannot break on upgrade.
- **never crashes** — any internal error exits 0 silently, and the default
  `fail_closed: false` lets the call through. A steering guard that wedges every
  tool call on a bug is far worse than one that occasionally misses. Set
  `fail_closed: true` in the config entry to invert that trade.
- **no false positives on the happy path** — the allowlist for `sexpsplice`/`cljgen`
  plus the "must mention a Clojure file" precondition keep it from interfering with
  ordinary work.

## Related

- [`../skills/clojure-programming/SKILL.md`](../skills/clojure-programming/SKILL.md) — the teaching half
- [`../sexpsplice/`](../sexpsplice/) — the structural editor (rewrite-clj)
- [`../cljgen/`](../cljgen/) — DATA → `.clj` emitter
- [`../sexpsplice/IMPLEMENTATION-NOTES.md`](../sexpsplice/IMPLEMENTATION-NOTES.md) — implementation gotchas

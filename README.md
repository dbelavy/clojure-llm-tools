# Clojure LLM Tooling

Two tools, one skill, and one **enforcement gate** for letting an LLM reliably
create and edit Clojure/EDN files **structurally** — never by hand-typing source.

The rule that motivates everything here:

> **An LLM must never hand-emit a `.clj` file.** It authors *data* (a Python
> list of s-expressions), and the tool emits the source with every delimiter
> balanced by construction. To change a file, it names a form by index and the
> tool splices one replacement form in, leaving everything else byte-for-byte
> unchanged.

Two tools, two directions:

| Tool       | Language | Direction                        | When to use                          |
|------------|----------|----------------------------------|--------------------------------------|
| **cljgen** | Python 3 | DATA → `.clj` (emit)             | Create a new file from scratch       |
| **sexpsplice** | Clojure | `.clj` → edit → `.clj` (splice) | Edit one form in an existing file    |

## Status

Production-usable. Both tools ship with formal specs (`SPEC.md`) and acceptance
tests that pass against the real Clojure toolchain (`clj-kondo` + `sexpsplice`),
not just self-consistency checks.

They are complementary: **cljgen** builds new files from typed data; **sexpsplice**
surgically edits existing files while preserving comments, reader macros, and
formatting. Use cljgen to generate, sexpsplice to modify.

Research notes: [`docs/best-practices-llm-coding.md`](docs/best-practices-llm-coding.md)
— current best practice for LLM coding (context management, verification,
structural tooling), with a mapping to cljgen/sexpsplice.

```
clojure-llm-tools/
├── README.md            # this file
├── docs/
│   └── best-practices-llm-coding.md   # LLM coding best practices + mapping to these tools
├── INSTALL.md           # install both tools (Clojure CLI, clj-kondo, launchers)
├── cljgen/              # Python emitter: DATA -> .clj
│   ├── cljgen.py        #   the module (stdlib only, no deps)
│   ├── SPEC.md          #   formal spec + acceptance criteria
│   ├── v2_test.py       #   original regression fixture (still passes)
│   └── v3_test.py       #   acceptance tests (36 checks)
├── cljgen-clj/          # Clojure port of cljgen (EDN in -> balanced .clj out)
├── scripts/
│   └── repo-root        #   resolve the checkout path (never hardcode it)
├── sexpsplice/          # Clojure structural editor
│   ├── sexpsplice.clj   #   the tool (9 commands)
│   ├── deps.edn         #   rewrite-clj 1.2.57 + Clojars
│   ├── SPEC.md          #   formal spec + acceptance criteria
│   ├── IMPLEMENTATION-NOTES.md  # 13 implementation gotchas
│   └── bin/sexpsplice   #   launcher script
├── agent-hooks/         # Hermes enforcement gate — see "Enforcement" below
│   ├── clj_guard.py     #   pre_tool_call block + pre_verify nudge
│   ├── install.sh       #   wire into Hermes (config + consent allowlist)
│   ├── test_clj_guard.py#   52 verdict cases + stdin→stdout wire test
│   └── README.md
└── skills/
    └── clojure-programming/
        └── SKILL.md     # Hermes agent skill (install into ~/.hermes/skills/)
```

## Repository & remotes (read this before "fixing" a path)

**Canonical remote: `github-rk:dbelavy/clojure-llm-tools.git` (GitHub). It is the only source of truth.**

Two agents work in this repo from different hosts, and the local checkout path differs between
them. Hardcoding one has already broken the skill twice — once naming `~/repos/…`, once
`~/projects/…`, each dead on the other host. **Resolve the path; don't assume it:**

```bash
REPO="$(clj-repo-root)"   # -> the checkout root, or exit 1 with a clear message
```

`scripts/repo-root` is the single implementation (installed on PATH as `clj-repo-root`, and it
honours `CLJ_TOOLS_ROOT` for unusual layouts). Add a candidate path *there* if a new host needs
one — never as a literal home path in the skill's prose.

**Never fetch, pull, or push the retired Bitbucket mirror**
(`bitbucket-rk:richardkimble/clojure-llm-tools.git`). Its `main` is `b4967a2` ("Initial commit"),
a **parentless root commit that deletes the entire project** (14 files, ~1390 lines) and shares no
history with the real repo — a pull from it would wipe the working tree. Its last surviving clone
is the stale shadow `~/Sync/shared/outbox/repos/clojure-llm-tools` (3 ancient commits, no
`agent-hooks/`, no `docs/`). That directory is not the repo.

## Quick start

```bash
# 1. Install prerequisites (Clojure CLI + clj-kondo) — see INSTALL.md

# 2. Install the sexpsplice launcher on PATH
ln -s "$PWD/sexpsplice/bin/sexpsplice" ~/bin/sexpsplice

# 3. Generate a file with cljgen
python3 - <<'PY'
import sys; sys.path.insert(0, "cljgen")
from cljgen import Sym, Kw, write_forms
forms = [[Sym("ns"), Sym("demo.core")],
         [Sym("defn"), Sym("square"), (Sym("n"),), [Sym("*"), Sym("n"), Sym("n")]]]
write_forms("/tmp/demo.clj", forms, newlines=True)
PY

# 4. Edit it with sexpsplice
sexpsplice list   /tmp/demo.clj
sexpsplice get    /tmp/demo.clj 1
sexpsplice set    /tmp/demo.clj 1 <<< '(defn square [n] (* n n))'
```

## Enforcement: `agent-hooks/` — a gate, because a skill is only advice

The skill teaches the rule. On its own it is **not enough**: an agent can hold the
rule and still reach for `sed` mid-session, because nothing stops it. So the rule
is enforced by a Hermes
[shell hook](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks)
on `pre_tool_call`:

```bash
cd agent-hooks && ./install.sh     # then: systemctl --user restart hermes-gateway
python3 agent-hooks/test_clj_guard.py   # 52 cases + wire protocol
```

It **blocks** any attempt to rewrite `.clj`/`.cljc`/`.cljs`/`.edn` as text —
`sed -i`, `perl -i`, a scripting interpreter, a content redirect, `tee`/`dd`, an
editor, or the `patch`/`write_file` tools — and returns the correct
sexpsplice/cljgen command *at the moment of the mistake*. That timing is the
point: guidance delivered when the agent reaches for the wrong tool is what
changes behaviour. A `pre_verify` hook additionally refuses to let a turn finish
after touching Clojure without `clj-kondo` + `sexpsplice list` + `wc -l` + a real
`require`.

See [`agent-hooks/README.md`](agent-hooks/README.md) — including the two traps
that make an installed hook silently do nothing (missing consent allowlist in a
non-TTY gateway; `hermes hooks test` wanting `args` where the runtime sends
`tool_input`).

## Verification rule (never skip)

Both tools produce source the LLM must **not** trust by eye. Always re-parse
with the real toolchain:

```bash
clj-kondo --lint <file>     # real Clojure reader/linter
sexpsplice list <file>      # real reader, form count
```

## Dependencies & licenses

- **cljgen** — Python 3 standard library only, no dependencies. MIT.
- **sexpsplice** — depends on [rewrite-clj](https://github.com/clj-commons/rewrite-clj)
  (EPL-1.0), fetched from Clojars at runtime. The tool itself is MIT; EPL-1.0 is
  a weak copyleft license that is compatible with an MIT-licensed project.

## License

MIT — see [LICENSE](LICENSE).

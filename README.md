# Clojure LLM Tooling

Two tools, one skill, and one **enforcement gate** for letting an LLM reliably
create and edit Clojure/EDN files **structurally** — never by hand-typing
source. Both tools are Clojure.

The rule that motivates everything here:

> **An LLM must never hand-emit a `.clj` file.** It authors *data* (EDN), and
> the tool emits the source with every delimiter balanced by construction. To
> change a file, it names a form by index and the tool splices one replacement
> form in, leaving everything else byte-for-byte unchanged.

Two tools, two directions:

| Tool       | Language | Direction                        | When to use                          |
|------------|----------|----------------------------------|--------------------------------------|
| **cljgen** | Clojure  | EDN → `.clj` (emit)              | Create a new file from scratch       |
| **sexpsplice** | Clojure | `.clj` → edit → `.clj` (splice) | Edit one form in an existing file    |

## Status

Production-usable. Both tools ship with formal specs (`SPEC.md`) and acceptance
tests that pass against the real Clojure toolchain (`clj-kondo` + `sexpsplice`),
not just self-consistency checks.

They are complementary: **cljgen** builds new files from EDN data; **sexpsplice**
surgically edits existing files while preserving comments, reader macros, and
formatting. Use cljgen to generate, sexpsplice to modify.

Both tools are **Clojure**. The original Python `cljgen` (`cljgen/`) is kept
only as the byte-exact reference implementation and regression battery that the
Clojure port (`cljgen-clj/`) is verified against — author with `cljgen-clj`,
not the Python module.

Research notes: [`docs/best-practices-llm-coding.md`](docs/best-practices-llm-coding.md)
— current best practice for LLM coding (context management, verification,
structural tooling), with a mapping to cljgen/sexpsplice.

```
clojure-llm-tools/
├── README.md            # this file
├── docs/
│   └── best-practices-llm-coding.md   # LLM coding best practices + mapping to these tools
├── INSTALL.md           # install both tools (Clojure CLI, clj-kondo, launchers)
├── cljgen/              # Python reference emitter: DATA -> .clj (legacy,
│   │                    #   kept only to byte-verify the Clojure port)
│   ├── cljgen.py        #   the module (stdlib only, no deps)
│   ├── SPEC.md          #   formal spec + acceptance criteria
│   ├── v2_test.py       #   original regression fixture (still passes)
│   └── v3_test.py       #   acceptance tests (36 checks)
├── cljgen-clj/          # THE cljgen: Clojure emitter (EDN in -> balanced .clj out)
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

## Repository layout & remotes (read this before "fixing" a path)

**Syncthing is canonical for all repositories and projects.** The shared folder is flat:
`repos/` (git repositories) and `projects/` (non-repo projects), alongside `backups/`.

**Canonical remote: `github-rk:dbelavy/clojure-llm-tools.git` (GitHub). It is the only source of truth.**

Two agents work in this repo from different hosts, and the local checkout path differs between
them. Hardcoding one has already broken the skill twice — once naming `~/repos/…`, once
`~/projects/…`, each dead on the other host. **Resolve the path; don't assume it:**

```bash
REPO="$(clj-repo-root)"    # this repo
ROOT="$(repos-root)"       # canonical repos root — every repository lives here
PROJ="$(projects-root)"    # canonical projects root
repo-root <name>           # any repo by name, e.g. repo-root postbox
repo-root --list           # show what resolved, for debugging
```

`scripts/repo-root` is the single implementation; `clj-repo-root`, `repos-root` and
`projects-root` are thin wrappers over it. It locates the shared folder by **discovery** — a
Syncthing root is any directory containing a `.stfolder` marker — so it survives that folder
being moved or renamed, and no host layout is baked in. Overrides for other hosts:
`$REPOS_ROOT`, `$PROJECTS_ROOT`, and legacy `$CLJ_TOOLS_ROOT`. It never guesses: a wrong path
is worse than a clear failure, because an agent will happily use it.

**`origin` is GitHub, and it is the only remote.** One remote means the remote is the source of
truth — that is what makes "resolve the path, don't assume it" safe. Don't add a second one: a
duplicate checkout pointed at a divergent remote is exactly what caused the path churn.

## Quick start

```bash
# 1. Install prerequisites (Clojure CLI + clj-kondo) — see INSTALL.md

# 2. Install the sexpsplice launcher on PATH
ln -s "$PWD/sexpsplice/bin/sexpsplice" ~/bin/sexpsplice

# 3. Generate a file with cljgen (Clojure; author EDN data, never hand-typed
#    s-expressions)
printf '[ (ns demo.core) (defn square [n] (* n n)) ]' > /tmp/forms.edn
(cd cljgen-clj && clojure -M -m cljgen.cli /tmp/forms.edn /tmp/demo.clj)

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

- **cljgen** (Clojure, `cljgen-clj/`) — pure Clojure, no external deps beyond
  the Clojure CLI. The Python reference (`cljgen/`) is stdlib-only. MIT.
- **sexpsplice** — depends on [rewrite-clj](https://github.com/clj-commons/rewrite-clj)
  (EPL-1.0), fetched from Clojars at runtime. The tool itself is MIT; EPL-1.0 is
  a weak copyleft license that is compatible with an MIT-licensed project.

## License

MIT — see [LICENSE](LICENSE).

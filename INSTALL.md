# Install — Clojure LLM Tooling

Prerequisites for both tools, then the per-tool setup.

## Prerequisites

### 1. Clojure CLI (required by sexpsplice)

Install the official `clojure` CLI (Linux):

```bash
curl -L -O https://github.com/clojure/brew-install/releases/latest/download/linux-install.sh
chmod +x linux-install.sh
sudo ./linux-install.sh
```

Verify: `clojure --version`

### 2. clj-kondo (required for lint verification)

```bash
# NOTE: the release asset name has NO "v" prefix.
curl -sL https://github.com/clj-kondo/clj-kondo/releases/download/v2026.08.04/clj-kondo-2026.08.04-linux-amd64.zip -o /tmp/clj-kondo.zip
cd /tmp && unzip clj-kondo.zip && sudo mv clj-kondo /usr/local/bin/
clj-kondo --version
```

## sexpsplice (Clojure structural editor)

```bash
mkdir -p ~/bin ~/projects
cp -r sexpsplice ~/projects/sexpsplice
ln -sf ~/projects/sexpsplice/bin/sexpsplice ~/bin/sexpsplice
# ensure ~/bin is on PATH (add to ~/.bashrc if not already)
export PATH="$HOME/bin:$PATH"

sexpsplice --help        # smoke test
```

- Launcher runs `clojure -Srepro -Sdeps '…' -M sexpsplice.clj "$@"`.
- `SEXPSPLICE_HOME` env var overrides the project dir (default `~/projects/sexpsplice`).
- Dependency (rewrite-clj 1.2.57) is fetched from Clojars on first run.

## cljgen (Clojure emitter)

The authoring tool is the **Clojure** `cljgen-clj/` — no Python, no pip
installs. Author EDN data (a vector of forms); the tool emits balanced `.clj`.

```bash
# Author a file: EDN in -> .clj out (balance-gated)
printf '[ (ns demo.core) (defn square [n] (* n n)) ]' > /tmp/forms.edn
(cd cljgen-clj && clojure -M -m cljgen.cli /tmp/forms.edn /tmp/demo.clj)
# -> wrote /tmp/demo.clj
```

EDN has no list literal: top-level vector = one form per element (each form
becomes a list); `{:__vec__ [...]}` emits a vector (arg/binding vectors —
ALWAYS use it for those), and a bare 1-element symbol vector (`[n]`) stays a
vector.

Run the verification battery (the Python `cljgen/` is the byte-exact reference
the Clojure port is checked against — do NOT author with it):

```bash
cd cljgen && python3 v3_test.py     # 36 checks, exit 0
cd cljgen && python3 v2_test.py     # regression fixture
```

## Install the Hermes agent skill (optional)

```bash
cp -r skills/clojure-programming ~/.hermes/skills/
```

Then a Hermes agent (or any Claude-style agent) has the full 9-command
reference, path syntax, and the 13 implementation gotchas on hand.

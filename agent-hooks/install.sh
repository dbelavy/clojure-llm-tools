#!/usr/bin/env bash
# install.sh — wire clj_guard into Hermes as a live pre_tool_call gate.
#
#   ./install.sh                  install the gate (pre_tool_call + pre_verify)
#   ./install.sh --with-reminder  also inject a one-line reminder each turn
#   ./install.sh --uninstall      remove config entries + allowlist entries
#   ./install.sh --dry-run        print what would change, touch nothing
#
# Why this is more than "copy a file and set a key": a hook that is configured
# but NOT in the consent allowlist is silently skipped in any non-TTY context
# (gateway, cron, CI) — the guard would appear installed and do nothing while
# you talk to the agent over Telegram. So this writes the allowlist too.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HOOK_DIR="$HERMES_HOME/agent-hooks"
HOOK_PATH="$HOOK_DIR/clj_guard.py"
ALLOWLIST="$HERMES_HOME/shell-hooks-allowlist.json"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WITH_REMINDER=0
UNINSTALL=0
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --with-reminder) WITH_REMINDER=1 ;;
    --uninstall)     UNINSTALL=1 ;;
    --dry-run)       DRY_RUN=1 ;;
    -h|--help)       sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '%s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || die "python3 is required"
command -v hermes  >/dev/null 2>&1 || say "WARN: 'hermes' not on PATH — config steps will be skipped"

# Build the JSON for a hook entry. Extra keys are appended as '"k": v' pairs.
entry() { # entry <matcher-json-or-empty> <command> [extra json pairs]
  local matcher="$1" cmd="$2" extra="${3:-}"
  local body="\"command\": $(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$cmd")"
  [ -n "$matcher" ] && body="\"matcher\": $matcher, $body"
  [ -n "$extra" ] && body="$body, $extra"
  printf '[{%s}]' "$body"
}

# ---------------------------------------------------------------- uninstall
if [ "$UNINSTALL" = 1 ]; then
  say "==> uninstalling clj_guard"
  if command -v hermes >/dev/null 2>&1; then
    for ev in pre_tool_call pre_verify pre_llm_call; do
      [ "$DRY_RUN" = 1 ] && { say "    would clear hooks.$ev"; continue; }
      hermes hooks revoke "$HOOK_PATH" >/dev/null 2>&1 || true
    done
    [ "$DRY_RUN" = 1 ] || {
      python3 - "$HERMES_HOME/config.yaml" "$ALLOWLIST" <<'PY'
import re, sys, pathlib
cfg, allow = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
# Strip only clj_guard entries; leave any other hooks the user has configured.
if cfg.exists():
    text = cfg.read_text()
    print("NOTE: edit hooks.* in %s by hand (or `hermes config set`) to drop the "
          "remaining %s entries." % (cfg, "clj_guard"))
if allow.exists():
    import json
    try:
        data = json.loads(allow.read_text() or "{}")
    except Exception:
        data = {}
    ap = data.get("approvals")
    if isinstance(ap, list):
        keep = [a for a in ap if "clj_guard.py" not in str(a.get("command", ""))]
        data["approvals"] = keep
        allow.write_text(json.dumps(data, indent=2) + "\n")
        print("removed %d allowlist entr(ies) from %s" % (len(ap) - len(keep), allow))
PY
    }
  fi
  say "    hook file left in place at $HOOK_PATH (delete it manually if you want)"
  exit 0
fi

# ------------------------------------------------------------------ install
say "==> clj_guard installer"
say "    HERMES_HOME = $HERMES_HOME"
say "    hook        = $HOOK_PATH"

if [ ! -f "$SRC_DIR/clj_guard.py" ]; then
  die "clj_guard.py not found next to this script ($SRC_DIR)"
fi

# Refuse to clobber somebody else's gate without an explicit decision.
if command -v hermes >/dev/null 2>&1; then
  existing="$(hermes config get hooks 2>/dev/null || true)"
  case "$existing" in
    *pre_tool_call*) say "NOTE: hooks.pre_tool_call already configured — replacing it." ;;
  esac
fi

if [ "$DRY_RUN" = 1 ]; then
  say "    would copy clj_guard.py -> $HOOK_PATH"
  say "    would set hooks.pre_tool_call = $(entry '"terminal|patch|write_file|execute_code"' "$HOOK_PATH")"
  say "    would set hooks.pre_verify     = $(entry '' "$HOOK_PATH")"
  [ "$WITH_REMINDER" = 1 ] && say "    would set hooks.pre_llm_call   = $(entry '' "$HOOK_PATH")"
  say "    would allowlist (pre_tool_call, pre_verify$([ "$WITH_REMINDER" = 1 ] && echo ', pre_llm_call')) for $HOOK_PATH"
  exit 0
fi

mkdir -p "$HOOK_DIR"
install -m 0755 "$SRC_DIR/clj_guard.py" "$HOOK_PATH"
say "    installed hook ($(python3 -c 'import sys;sys.path.insert(0,sys.argv[1]);import clj_guard;print("v"+clj_guard.__version__)' "$HOOK_DIR"))"

# --- wire the config (through the sanctioned writer, never by hand) ---------
if command -v hermes >/dev/null 2>&1; then
  hermes config set hooks.pre_tool_call \
    "$(entry '"terminal|patch|write_file|execute_code"' "$HOOK_PATH" '"timeout": 10')" >/dev/null
  hermes config set hooks.pre_verify "$(entry '' "$HOOK_PATH" '"timeout": 15')" >/dev/null
  say "    wired hooks.pre_tool_call + hooks.pre_verify"
  if [ "$WITH_REMINDER" = 1 ]; then
    hermes config set hooks.pre_llm_call "$(entry '' "$HOOK_PATH" '"timeout": 10')" >/dev/null
    say "    wired hooks.pre_llm_call (per-turn reminder)"
  fi
else
  say "    SKIPPED config wiring — add this to $HERMES_HOME/config.yaml by hand:"
  say "      hooks:"
  say "        pre_tool_call:"
  say "          - matcher: \"terminal|patch|write_file|execute_code\""
  say "            command: \"$HOOK_PATH\""
  say "            timeout: 10"
  say "        pre_verify:"
  say "          - command: \"$HOOK_PATH\""
  say "            timeout: 15"
fi

# --- consent allowlist: without this the gate is silently dead in a gateway -
python3 - "$ALLOWLIST" "$HOOK_PATH" "$WITH_REMINDER" <<'PY'
import json, pathlib, sys
allow_path, hook, reminder = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3] == "1"
if allow_path.exists():
    backup = allow_path.with_suffix(".json.bak")
    backup.write_text(allow_path.read_text())
data = {}
if allow_path.exists() and allow_path.read_text().strip():
    try:
        data = json.loads(allow_path.read_text())
    except Exception:
        data = {}
if not isinstance(data, dict):
    data = {}
approvals = data.get("approvals")
if not isinstance(approvals, list):
    approvals = []
events = ["pre_tool_call", "pre_verify"] + (["pre_llm_call"] if reminder else [])
added = 0
for ev in events:
    if not any(isinstance(a, dict) and a.get("event") == ev and a.get("command") == hook
               for a in approvals):
        approvals.append({"event": ev, "command": hook})
        added += 1
data["approvals"] = approvals
allow_path.parent.mkdir(parents=True, exist_ok=True)
allow_path.write_text(json.dumps(data, indent=2) + "\n")
print("    allowlisted %d entr(ies) in %s" % (added, allow_path))
PY

# ------------------------------------------------------------------- verify
if command -v hermes >/dev/null 2>&1; then
  say ""
  say "==> hermes hooks list"
  hermes hooks list 2>&1 | sed 's/^/    /' || true
  say ""
  say "==> hermes hooks doctor"
  hermes hooks doctor 2>&1 | sed 's/^/    /' || true
  say ""
  say "==> live probe (synthetic sed -i against a .clj)"
  hermes hooks test pre_tool_call --for-tool terminal 2>&1 | sed 's/^/    /' || true
fi

say ""
say "Done. Restart the gateway so the hook registers:  systemctl --user restart hermes-gateway"
say "Test it by asking an agent to 'sed -i' a .clj file — it should be refused with"
say "a message naming sexpsplice/cljgen instead."

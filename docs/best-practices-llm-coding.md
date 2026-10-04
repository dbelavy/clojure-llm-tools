# Best Practices for LLM Coding

Research pass 2 (2026-10-03, refreshed from live sources — see [Sources](#sources)).
Scope: what the current primary literature and practice say about getting LLMs
to write reliable code, and how each practice maps onto David's setup
(cljgen / sexpsplice / clj-kondo / Hermes skills / 50-line rule).

## Core findings

1. **The dominant constraint is context, not intelligence.**
   Performance degrades as the context window fills; the agent's "attention
   budget" is spent by every token in the conversation. Nearly every best
   practice below exists to manage context: keep only the smallest set of
   high-signal tokens, retrieve the rest just-in-time.
   (Anthropic: *Effective context engineering*; Claude Code best practices:
   "most best practices are based on one constraint: the context window
   fills up fast and performance degrades as it fills.")

2. **Give the LLM a way to verify its work.**
   A check it can run itself (tests, build exit code, linter, fixture diff,
   screenshot compare) turns "looks done" into "is done". The agent then
   loops: work → run check → read result → iterate. Require *evidence*
   (the actual test output / command result), not an assertion of success.
   Escalating forms: in-prompt check → goal/condition re-checked after each
   turn → deterministic Stop-hook gate → fresh-context reviewer that tries
   to refute the result.

3. **Explore → plan → implement, as separate phases.**
   Jumping straight to code solves the wrong problem. Read-only exploration
   first (no writes), then a concrete plan (files to touch, approach,
   verification step), then implementation measured against the plan.
   Skip the plan when the change is one-sentence small. For large features,
   have the LLM *interview* the user first and write a self-contained spec
   (names the files/interfaces, states what's out of scope, ends with an
   end-to-end verification step); then start a *fresh session* to implement.

4. **Precise prompts beat vague ones.**
   Name the file, the scenario, the constraints; point at an existing
   pattern to imitate ("follow how HotDogWidget is done"); describe the
   symptom plus what "fixed" looks like. Let the LLM fetch context itself
   (read files, git history, `--help`) instead of you pasting everything.

5. **Context is a finite resource — manage it aggressively.**
   - Clear/compact between unrelated tasks; accumulated failed corrections
     poison the session (after ~2 failed corrections on one issue: start
     fresh with a better prompt that incorporates the lesson).
   - Compaction = summarise a near-full conversation into a fresh window;
     tune for recall first, then precision; clearing old tool results is the
     safest light compaction.
   - Structured note-taking (NOTES.md / todo lists / memory files) persists
     state outside the window and survives resets.
   - Just-in-time retrieval beats up-front stuffing: let the agent search
     and read progressively (glob/grep/read) instead of pre-indexing
     everything into context.

6. **Prefer a single-threaded agent; use subagents for *investigation*, not parallel work.**
   (Cognition: *Don't Build Multi-Agents*.) Actions carry implicit
   decisions; parallel subagents make conflicting invisible decisions
   (two subagents build one system in two inconsistent styles). Default to
   one continuous context. Subagents are worth it when they do read-heavy
   research and return a short summary (1–2k tokens), leaving the main
   context clean. Multi-agent parallelism pays only for breadth-first tasks
   (research, analysis) — most *coding* tasks are not parallelizable that
   way. If you must parallelize: give each subagent objective, output
   format, tool guidance, and explicit task boundaries, and scale effort to
   query complexity (small task = 1 agent, few calls).

7. **Design tools for the agent, not for humans (and for Clojure, make tools do the
   structural work).**
   - Fewer, thoughtful tools with clear distinct purposes beat many
     wrapper tools; namespacing (service_/resource_ prefixes) helps
     selection; return high-signal output (natural-language names over
     opaque UUIDs); concise vs detailed output mode where useful.
   - Write tool descriptions as prompts (the agent reads them); build an
     eval of tool use and iterate the descriptions against it.
   - **Clojure-specific corollary:** an LLM should never hand-emit `.clj`
     source text. It authors *data* and a tool emits the file with
     delimiters balanced by construction (cljgen), or names a form by
     index and splices exactly one replacement in (sexpsplice). This is the
     tool-design principle applied to the hardest part of Clojure for
     LLMs: paren bookkeeping.

8. **Verify with real readers, not proxies.**
   A lint pass proves syntax + style, not behavior: load the namespace in
   the real runtime (JVM) and run the tests. Never verify delimiters by
   hand-counting or raw string counts — docstrings and string literals
   contain unbalanced parens, so only a real reader (clj-kondo, the JVM
   reader, sexpsplice's own parse) is authoritative. When a tool and your
   mental model disagree, the tool wins.

9. **Make rules durable and minimal (CLAUDE.md / AGENTS.md / skills).**
   Persistent instructions should contain only what the LLM *cannot infer
   from the code*: project commands, non-default style rules, gotchas,
   repo etiquette. Bloat makes the model ignore the whole file — for each
   line ask "would removing this cause a mistake?" and prune the rest.
   Put occasionally-relevant procedures in skills (loaded on demand), not
   in the always-loaded file. Where an action must happen with zero
   exceptions, use a deterministic hook (script gate), not a prose
   instruction.

10. **Fresh-context review before "done".**
    A reviewer that sees only the diff + the criteria (not the reasoning
    that produced the change) catches what the implementor is biased away
    from. Tell it to report *gaps that affect correctness*, not style —
    otherwise it manufactures findings and you over-engineer.

## How this maps to David's setup (clojure-llm-tools)

| Practice | Our implementation |
|---|---|
| Verifiable work (§2) | clj-kondo lint + JVM load of the ns + test suite; require *evidence* (command output), not "it works" |
| Structural authoring (§7) | cljgen for new files (data → .clj, balanced by construction); sexpsplice append-loop (one form, review, repeat) |
| Surgical edits (§7) | sexpsplice `set`/`delete`/`insert`/`move` by index — everything else preserved byte-for-byte (comments, reader macros) |
| Real readers only (§8) | clj-kondo **and** a successful sexpsplice parse (two independent parsers) before trusting a form; JVM load to prove it compiles |
| Broken file policy (§8) | Revert (`.bak`/git) or rewrite from scratch via append loop — never incrementally hand-repair a corrupted `.clj` |
| Context management (§5) | 50-line `.clj` cap (compiler-enforced) forces small files and small per-file context; 100-line cap for Python; `wc -l` after every form |
| Durable rules (§9) | `clojure-programming` skill carries the standing rules + pitfalls (e.g. `run!` laziness) and re-asserts them each Clojure turn |
| Explore → plan → implement (§3) | sexpsplice `list`/`find`/`get` = read-only exploration before any `set`/`append` |
| Fresh-context review (§10) | Review = re-read with a second parser/runtime, not the same model asserting success |

## Honest caveats

- Source mix: 5 primary engineering posts (Anthropic ×5, Cognition ×1),
  fetched 2026-10-03. No peer-reviewed studies in this pass; the LLM-coding
  best-practice literature is practitioner-driven and moves fast — some
  specifics (e.g. tool names, feature names like plan mode / Stop hooks)
  are vendor-specific and will drift.
- Cognition's anti-multi-agent position is a design argument, not a
  measurement result; Anthropic's own multi-agent research system reports
  +90.2% on *research* evals — the two agree on the boundary: parallel
  subagents for breadth-first research, single-threaded for code mutation.
- The report could not locate the *first* research pass (no persisted
  artifact was found in the repo, ~/Shared, or memory as of 2026-10-03), so
  this is a clean rewrite, not a diff. If the original report lives
  elsewhere, tell us where and we'll merge.

## Sources

- Anthropic — "Best practices for Claude Code" (docs, fetched 2026-10-03):
  https://www.anthropic.com/engineering/claude-code-best-practices
- Anthropic — "Effective context engineering for AI agents" (Sep 2025):
  https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic — "Building effective agents" (Dec 2024):
  https://www.anthropic.com/engineering/building-effective-agents
- Anthropic — "Writing effective tools for agents — with agents" (Sep 2025):
  https://www.anthropic.com/engineering/writing-tools-for-agents
- Anthropic — "How we built our multi-agent research system" (Jun 2025):
  https://www.anthropic.com/engineering/multi-agent-research-system
- Cognition (Walden Yan) — "Don't Build Multi-Agents" (Jun 2025):
  https://cognition.ai/blog/dont-build-multi-agents

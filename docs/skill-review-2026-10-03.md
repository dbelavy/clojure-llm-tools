# Clojure skills review — 2026-10-03 (nightly agent pass)

Task: "review your clojure programming skills in light of recent work" (queue task 6hgWfMC5xXx2G7pJ).
Scope: what the last month of Clojure work (mostly knowledgeasfunction, 25 commits since 2026-09-25)
exercises, what the skill set got right, what drifted, and what to fix.

## Recent work exercised

| Project | Activity (verified via git) |
|---|---|
| `knowledgeasfunction` (KAF) | Heavy: 25 commits 2026-09-25→28 (split-refactor of `server.clj` 6 steps + `core.clj` 3 steps, PDF ingestion, reactive cascade). 412/408/328/301-line files now. Uncommitted WIP (relationships, document store). |
| `clojure-llm-tools` | Skill v1.3.0 (rename + standing rules, 2026-09-28), path fix, best-practices-llm-coding.md research pass 2 (2026-10-03). |
| `datastar-clojure` | None since rc11 (2026-06-05). SDK skill untouched; content assumed current, not re-verified. |
| `bas-consolidator`, `webauth` | Python-only recently; no Clojure impact. |

## What the skill set got right (recent work is evidence)

1. **Split-refactor workflow held up.** Harness-first + one-step-at-a-time + verified-per-step
   produced 12 clean split commits with no behavior regression. The "exempt hiccup/route-table
   files" clause is why `routes.clj`/`ui.clj` stayed large instead of being split uselessly.
2. **Structural authoring (cljgen/sexpsplice) is the right call for this codebase.** All tooling
   verified healthy tonight: sexpsplice launcher ↔ `~/projects` source ↔ repo copy in sync;
   cljgen installed copy = repo copy; installed skill = repo skill; clj-kondo 0 errors on KAF src.
3. **Best-practices mapping** (research pass 2) is accurate: every §2–§10 practice maps to a
   concrete tool in this setup. The doc's "honest caveats" framing is good.
4. **`clj-kondo` + JVM load as the verification gate** worked as designed: 47 warnings, 0 errors,
   fast (113ms), config-aware (`.clj-kondo/config.edn` encodes the `ch` macro-binding waiver).

## Findings (all verified tonight, not assumed)

### F1 — Real bug pattern in recent KAF code: double-arglist defns (5 sites)
`(defn f [args] "doc" [args] body)` — the second arglist makes the docstring a **dead body
string**: `(:doc (meta #'f))` = `nil` (verified on `kaf.store.lineage/dq` via JVM load). The form
parses and runs fine, so nothing caught it; clj-kondo only warns "Misplaced docstring".
Sites: `src/kaf/store/lineage.clj` (`dq`, `record!`, `edges!`, `graph!`) and `src/kaf/core.clj`
(`store!`). This directly contradicts the KAF `.clj-kondo/config.edn` note "Existing KAF code has
been migrated; doc BEFORE args" — the 09-27/28 WIP reintroduced the pattern.
**Action:** mechanical fix (drop the duplicated arglist) — small, belongs to KAF work; queue as a
separate task. **Skill gap:** the `clojure-programming` checklist has "kondo = 0 errors" but not
"treat `Misplaced docstring` warnings as live findings and verify with `(:doc (meta #'f))`" — the
`clojure-coding` skill documents exactly this pitfall; the two skills never cross-reference.

### F2 — 50-line rule not applied to recent KAF core files
`core.clj` 408 lines and `ai.clj` 202 lines are domain logic, not hiccup/route tables, so they
aren't exempt — yet the last month's work left them. Either the rule is silently dropped in long
sessions (the exact failure mode the standing rules warn about) or its scope is ambiguous.
**Action:** (a) re-commit to splitting `kaf.core`/`kaf.ai` as a queued task, or (b) write the real
exemption list into the `clojure-split-refactor` skill. Current state: rule exists, enforcement
lapsed.

### F3 — Skill contradictions (3 skills agree on structure, disagree on style)
- **Bang naming:** `clojure-coding` says "FORBIDDEN: NO ! suffix, even for side-effect
  functions"; every KAF function in recent work uses bangs (`store!`, `record!`, `graph!`,
  `migrate!`). The iwillig-imported rule is wrong for this codebase and actively misleading.
  **Action:** delete/replace that rule with the actual convention (bang = observable side
  effect), or drop `clojure-coding`'s style section in favour of `clojure-programming`'s.
- **cljgen data-mapping table** lives in `clojure-paren-repair` (an odd home) while
  `clojure-programming` points to it; two skills carry overlapping standing rules = the bloat the
  best-practices doc warns makes rules get ignored. **Action:** single home =
  `clojure-programming`; others link to it.
- **Stale refs:** `clojure-paren-repair` says companion is "v1.2.0" (it's v1.3.0);
  `clojure-programming` still points at `~/projects/sexpsplice` in 3 places (lines 81, 110, 141) —
  commit 1197e00 fixed the *canonical* path but not these working-copy refs.
  **Action (done this run):** paths + version ref fixed (see below).

### F4 — KAF has no committed test suite
No tracked `test/` dir; verification tonight was lint + JVM load + ad-hoc root-level probes
(`test_h2.clj` etc. are untracked scratch files at repo root). Best-practices §2 wants a
repeatable check the agent can run itself; KAF's closest thing is the split-refactor rendering
probes, which were never committed. **Action:** queue a task to wire kaocha (already in `~/.m2`)
and commit at least the fact-store + lineage probes — `graph!`/cascade logic is exactly where a
regression would hide.

### F5 — Hygiene
- `src/kaf/server/relationships.clj.bak` (sexpsplice backup) sitting in KAF working tree; KAF
  should gitignore `*.clj.bak`.
- `datastar-clojure-sdk` skill not re-verified since June; low priority.
- cljgen "read .clj → Python data" direction still unbuilt (open since 2026-09-28); fine to defer,
  but it's the one structural-authoring gap (editing still needs sexpsplice either way).

## Applied this run (small, unambiguous)
- `clojure-programming` skill v1.3.1: 3× `~/projects/sexpsplice` → canonical `~/repos/clojure-llm-tools/sexpsplice` (installed copy + repo copy, in sync).
- `clojure-paren-repair` skill: companion version ref 1.2.0 → 1.3.1.
- This review doc committed to `clojure-llm-tools/docs/`.

## Not applied (needs David's call / separate tasks)
1. Fix the 5 double-arglist defns in KAF (mechanical; one-line per site).
2. Decide 50-line rule enforcement for `kaf.core`/`kaf.ai` (split now vs written exemption).
3. Resolve the bang-naming contradiction in `clojure-coding`.
4. Commit a minimal kaocha suite for KAF.
5. Dedupe standing rules into `clojure-programming` as the single source.

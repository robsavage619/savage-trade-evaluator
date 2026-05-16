# Skill Routing — savage-trade-evaluator

Which of Rob's skills to invoke when. This is project-specific routing on top of the global skill set at `~/.claude/skills/`. Only skills actually present in Rob's ecosystem are listed.

**Convention:** trigger → skill. When the trigger matches, invoke the skill via the `Skill` tool (or the `/skill-name` slash-command shorthand) **before** generating a substantive response.

---

## Always-on (every turn)

| Trigger | Skill | Why |
|---|---|---|
| Any task on this project | `rob-context` | Loads Rob's identity, role, stack defaults; foundation for every other skill |
| Any Python file edit / creation | `py-conventions` | Enforces Python 3.12 / uv / ruff / pyright / src layout / `from __future__ import annotations` / Google docstrings / no `print()` / etc. — non-negotiable |

---

## Git & version control

| Trigger | Skill |
|---|---|
| "commit", "write a commit message", staging a change | `git-flow` |
| "new branch", "name this branch" | `git-flow` |
| "create a PR", "open a pull request" | `git-flow` |
| Pre-merge sanity check / branch readiness audit | `Agent(subagent_type: "general-purpose")` with audit instructions |

---

## Phase-1 V1 work (current)

| Trigger | Skill |
|---|---|
| Exploring V1 data layer / "where is X stored / computed" | `code-navigator` |
| Writing or reviewing SQL against DuckDB | `data:sql-queries` and/or `data:write-query` |
| Analyzing trade data, computing summary stats, characterizing distributions | `data:analyze`, `data:explore-data` |
| Charting / publication-quality figures from query results | `data:create-viz` (matplotlib/seaborn/plotly) |
| Building an HTML dashboard with KPI cards + filters | `data:build-dashboard` |
| QA / methodology / bias review of an analysis before sharing | `data:validate-data` |
| Significance test, anomaly detection, distribution test | `data:statistical-analysis` |
| Designing a debug strategy for an ingestion bug | `engineering:debug` |
| Writing unit/integration tests, test plan | `engineering:testing-strategy` |
| Pre-merge code review of own changes | `engineering:code-review` |
| Documenting a methodology decision as ADR | `engineering:architecture` |
| Writing project documentation (README, design docs) | `engineering:documentation` |
| Trimming noisy permission prompts (`.claude/settings.json`) | `fewer-permission-prompts` |
| Editing `settings.json` / adding hooks | `update-config` |

---

## Phase-2 modeling work (next)

| Trigger | Skill |
|---|---|
| Designing a rubric / test set / LLM-as-judge for the naïve baseline or any subsequent model | `agent-eval` |
| Architecting the multilevel Bayesian model / Stan/brms/Pyro pipeline | `llm-agent` (for the agentic-pipeline patterns) + `engineering:architecture` |
| Breaking Phase 2 into a structured backlog | `task-master` |
| System-design write-up for the model service | `engineering:system-design` |

---

## Phase-3 GM-behavior + Phase-4 product

| Trigger | Skill |
|---|---|
| Building the persona-critique agent runtime (Phase 5+) | `llm-agent` |
| MCP server to expose model as a tool | `mcp-builder` |
| API/service-boundary design for the eval endpoint | `engineering:system-design` |
| Front-end / dashboard visual design specs | `design:design-system`, `design:design-critique` |
| Defining design tokens for any UI | `design-system` (Rob's personal skill, distinct from `design:design-system`) |
| Writing CTA / button / error copy | `design:ux-copy` |
| WCAG accessibility audit on any UI | `design:accessibility-review` |

---

## Knowledge layer (vault work)

| Trigger | Skill |
|---|---|
| Adding a new paper to `savage_vault` | `ingest-paper` |
| Adding a new book to `savage_vault` | `ingest-textbook` |
| Synthesizing recent vault activity / thesis-check | `vault-synthesis` |
| Working with the vault structure / wikilinks / canvas / .base views | `obsidian` |
| Vague "research this" / "compare frameworks" / latest-state-of-X | `deep-research` |
| Cleaning a single webpage before analysis | `defuddle` |

---

## Blocked-source workarounds

| Trigger | Skill |
|---|---|
| **If we ever decide to unblock FanGraphs** for prospect FV grades (Phase 2 prospect work) | `playwright` — the only viable route per the Cloudflare findings (see LESSONS.md) |

---

## Hygiene & meta

| Trigger | Skill |
|---|---|
| Session was friction-heavy — capture lessons | `session-debrief` |
| Review just-written code for reuse / quality / efficiency | `simplify` |
| Persist a key decision across sessions | `mem9` |
| Discover a missing skill / improve an existing one | `skill-forge` |
| Recurring task / poll-until-done | `loop` |
| Cron-scheduled remote agent | `schedule` |

---

## Subagents (Agent tool, not Skill tool)

| Trigger | subagent_type |
|---|---|
| Broad codebase exploration > 3 queries | `Explore` |
| Designing a multi-step implementation plan | `Plan` |
| Verifying a file/function/flag exists before recommending it | `fact-checker` |
| Comprehensive long session getting heavy | `context-slimmer` |
| Wide research/multi-area exploration | `general-purpose` |

---

## What NOT to invoke in this project

These skills exist globally but **do not auto-route here.** If they fire on a confusion trigger, redirect away:

- `shc-workout`, `cover-letter`, `linkedin-audit`, `resume-coach`, `jd-fit`, `career-pipeline`, `job-hunt` — Rob's health/career projects, not baseball.
- `productivity:*` — task management. We have our own task tracking via the planning brief + decisions log.
- `marketing:*`, `sales:*`, `legal:*`, `finance:*`, `operations:*`, `product-management:*` (except `product-management:brainstorm` for early thesis work) — wrong domain.

---

## How this routing is enforced

Claude reads this file at session start (it's a project-root .md, loaded with CLAUDE.md). When a trigger matches, **invoke the Skill tool** with the listed skill name as a **blocking step** before generating a substantive response — same convention as the global skill auto-invocation rule.

If a trigger fires that's not listed here, default to Rob's global routing in `~/.claude/CLAUDE.md` + `~/.claude/skills/`.

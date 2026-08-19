# Architecture Decisions

This log records **approved** decisions (status `APPROVED`) and **proposed**
decisions awaiting approval (status `PROPOSED`). It must not record hypothetical
future work as completed. Decisions are listed newest-last.

---

## ADR-001 — Scoring dimensions never cause rejection

- **Status:** APPROVED (implemented and hard-validated in Phase 2B/2C)
- **Date:** 2026-08-11 (locked in the frozen scorers)
- **Decision:** Every scoring dimension (salary, experience, skills, role — and
  any future dimension) emits a score and confidence on `[-1.0, 1.0]` and sets
  `*_blocks=false` and `*_rejection_reason=null`. A low/negative score only
  **deprioritizes** a job. Eligibility (`ELIGIBLE / REVIEW / BLOCKED`) is decided
  by independent Phase 2B data-quality rules, never by score.
- **Consequences:** Composite scoring and any future scorer must preserve these
  fields. A job with a low score remains visible and eligible.

## ADR-002 — Eligibility, scoring, and ranking are separate concepts

- **Status:** APPROVED (concept enforced in Phase 2B/2C design)
- **Date:** 2026-08-11
- **Decision:** Keep these permanently distinct and never merge them into one
  module: data ingestion → normalization → dedup → eligibility → scoring →
  ranking → application decision → preparation → submission → tracking →
  scheduling → observability.
- **Consequences:** `pipeline.py` currently mixes several of these; it is frozen
  but is the primary future refactor target (see `docs/architecture.md`).

## ADR-003 — Join key is `job_id`; score files stay 1:1 with canonical records

- **Status:** APPROVED (verified 2026-08-11)
- **Date:** 2026-08-11
- **Decision:** `job_id` is the canonical join key. All score files must contain
  exactly the same `job_id` set as `phase2b/output/job_records.json` (20 records,
  1:1). Missing fields map to `UNAVAILABLE`/`UNCLEAR` neutral handling — never
  invented values.
- **Consequences:** Composite scoring merges the component files on `job_id`.

## ADR-004 — Current dataset stays canonical until explicitly refreshed

- **Status:** APPROVED (verified 2026-08-11)
- **Date:** 2026-08-11
- **Decision:** The 20-record dataset is the frozen reference set. Aggregate
  distributions (eligibility, per-dimension scores, 1:1 join) are asserted before
  any downstream work.

## ADR-005 — Frozen files are the compatibility contract

- **Status:** APPROVED (enforced by CLAUDE.md / PROJECT_STATE.md)
- **Date:** 2026-08-11
- **Decision:** Do not modify or move `phase2b/pipeline.py`, the four
  `phase2c_*.py` scorers, or their `output/*.json` without explicit approval. The
  production architecture is built around them incrementally.
- **Consequences:** A future refactor (ADR-006) ports behavior into
  `src/job_pipeline/` behind the same outputs, regression-tested, without
  rewriting the frozen files.

## ADR-006 — Future architecture: incremental port, not a destructive rewrite

- **Status:** APPROVED (this task)
- **Date:** 2026-08-11
- **Decision:** The target architecture in `docs/architecture.md` is adopted as
  the roadmap. Current `phase2b/` files map onto `src/job_pipeline/` modules
  (see mapping table in `docs/architecture.md` §3). Nothing moves in this task;
  a future approved refactor ports behavior module-by-module, preserving frozen
  outputs.

## ADR-007 — Composite scoring blocked until weights approved

- **Status:** SUPERSEDED by ADR-011 (weights now approved)
- **Date:** 2026-08-11
- **Decision:** Do not implement composite scoring until the weight set and the
  location/workplace policies are explicitly approved. Do **not** silently
  renormalize the current 0.80 to 1.00.
- **Proposed weights (NOT approved at time):** Skills 0.30 + Experience 0.20 + Role 0.15
  - Salary 0.15 + Location 0.10 + Workplace 0.10 = 1.00. See `docs/scoring.md`.
- **Consequences:** Composite score file, ranking, and recommendation tier are
  all `PLANNED / NOT IMPLEMENTED` at the time of this ADR. **Now superseded** —
  composite scoring is implemented with 6 components and 1.00 total weight.

## ADR-008 — Location scoring: design-only, requires geographic-policy approval

- **Status:** APPROVED (implemented 2026-08-18)
- **Date:** 2026-08-11
- **Proposal:** Score location by distinguishing: preferred geography, acceptable
  geography, remote, hybrid, onsite, unknown. Missing location/geography →
  reduced confidence, never automatic rejection.
- **Approved geographic preference (India):** Preferred tech hubs (BENGALURU, HYDERABAD, CHENNAI, MUMBAI, PUNE, GURGAON, NOIDA, DELHI); Acceptable cities with tech presence (COIMBATORE, THIRUVANANTHAPURAM, KOCHI, KOLKATA, AHMEDABAD, VADODARA, JAIPUR, INDORE, NAGPUR, LUCKNOW, BHUBANESWAR, VISAKHAPATNAM, MYSORE). Non-India treated as UNAVAILABLE neutral.
- **Consequences:** `phase2b/phase2c_location_score.py` IMPLEMENTED. Location weight 0.10 integrated into composite (ADR-011 updated).

## ADR-009 — Workplace scoring: design-only, unknown never rejects

- **Status:** APPROVED (implemented 2026-08-18)
- **Date:** 2026-08-11
- **Proposal:** Score workplace separately for Remote / Hybrid / Onsite / Unknown.
  `UNKNOWN` gets a neutral score with reduced confidence — **missing workplace
  type must NOT automatically disqualify a job** (consistent with the current
  frozen Phase 2B handling, where `UNKNOWN` workplace routes to REVIEW only via
  explicit conflict, not score).
- **Data note:** current dataset workplace = ONSITE 14 / UNKNOWN 6, with **no**
  remote/hybrid evidence. Remote/hybrid scoring thresholds therefore cannot be
  validated against this dataset yet.
- **Consequences:** `phase2b/phase2c_workplace_score.py` IMPLEMENTED. Workplace weight 0.10 integrated into composite (ADR-011 updated).

## ADR-010 — Application automation: out of scope until ranking is stable

- **Status:** **PROPOSED** (documented intent; NOT implemented)
- **Date:** 2026-08-11
- **Proposal:** Phase 3 application automation requires an explicit
  safety/approval mechanism and a persistent application-state model
  (`DISCOVERED … SUBMITTED … REJECTED / FAILED / DUPLICATE`). It must never
  auto-submit without a human gate.
- **Consequences:** No application submission, emails, account creation, or Apply
  clicks today.

## ADR-011 — Phase2C Composite scoring implemented (weights + tiers approved)

- **Status:** APPROVED (implemented 2026-08-11; updated 2026-08-18 for 6 components)
- **Date:** 2026-08-11
- **Decision:** Implement `phase2b/phase2c_composite_score.py`, combining the six
  component scores with weights salary 0.15 / experience 0.20 / skills 0.30 /
  role 0.15 / location 0.10 / workplace 0.10. `implemented_weight = 1.00`,
  `reserved_weight = 0.00`. Recommendation tiers (deterministic bands, recommendation-only):
  `RECOMMEND ≥ 0.25`, `CONSIDER [0.10, 0.25)`, `MONITOR < 0.10`.
- **Consequences:** Composite never blocks/rejects; `match_eligibility` and
  `data_quality_status` carried through unchanged; 1:1 join on `job_id`, 20 → 20
  outputs, no duplicate `job_id`; deterministic. Location (ADR-008) and Workplace
  (ADR-009) are now implemented and included in the 1.00 total weight.

## ADR-012 — Phase2C Ranking implemented (descending composite score, ascending job_id tie-break)

- **Status:** APPROVED (implemented 2026-08-11)
- **Date:** 2026-08-11
- **Decision:** Implement `phase2b/phase2c_ranking.py`, which orders all jobs by
  **descending `composite_score`**, tie-broken deterministically by **ascending
  `job_id`**. Rank 1 = highest composite score. Every input job is ranked exactly
  once (20 → 20, no drops/filters). Ranking is a ranking signal only: it never
  blocks or rejects (`ranking_blocks=false`, `ranking_rejection_reason=null`) and
  carries `match_eligibility`/`data_quality_status` through unchanged.
- **Consequences:** Output `phase2b/output/phase2c_rankings.json` is deterministic
  (stable across runs). No new scoring policy is introduced; ranks derive purely
  from the existing composite_score.

## ADR-013 — Phase2C Application-Decision Layer implemented (inclusive policy)

- **Status:** APPROVED (implemented 2026-08-11)
- **Date:** 2026-08-11
- **Decision:** Implement `phase2b/phase2c_application_decision.py`, a layer
  separate from eligibility/scoring/ranking (architecture concept #7) that decides
  which ranked jobs are proposed as application candidates. Approved **inclusive**
  policy: `CANDIDATE = ELIGIBLE AND recommendation_tier in {RECOMMEND, CONSIDER}`;
  `match_eligibility == REVIEW → REVIEW`; `match_eligibility == BLOCKED →
NOT_RECOMMENDED`. Output `phase2b/output/phase2c_application_decisions.json`.
- **Consequences:** The output is a **proposed shortlist only** — it never
  auto-submits, emails, creates accounts, or clicks Apply; a human approval gate
  precedes any application preparation. The decision is not an eligibility filter
  and never blocks/rejects (`application_blocks=false`,
  `application_rejection_reason=null`). Current 20-record split: CANDIDATE 15 /
  REVIEW 4 / NOT_RECOMMENDED 1. Application preparation, submission, and tracking
  remain NOT implemented (ADR-010).

---

## Decision index

| ADR | Topic                                                            | Status                                       |
| --- | ---------------------------------------------------------------- | -------------------------------------------- |
| 001 | Scoring never rejects                                            | APPROVED                                     |
| 002 | Separation of concerns                                           | APPROVED                                     |
| 003 | `job_id` join key                                                | APPROVED                                     |
| 004 | Dataset frozen reference set                                     | APPROVED                                     |
| 005 | Frozen-files compatibility contract                              | APPROVED                                     |
| 006 | Incremental port target architecture                             | APPROVED                                     |
| 007 | Composite blocked until weights approved                         | SUPERSEDED by ADR-011 (weights now approved) |
| 008 | Location scoring design                                          | APPROVED                                     |
| 009 | Workplace scoring design                                         | APPROVED                                     |
| 010 | Application automation out of scope                              | PROPOSED                                     |
| 011 | Composite scoring implemented (weights + tiers approved)         | APPROVED                                     |
| 012 | Ranking implemented (desc composite score, asc job_id tie-break) | APPROVED                                     |
| 013 | Application-decision layer implemented (inclusive policy)        | APPROVED                                     |

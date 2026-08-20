# Architecture

Status: **TARGET / PARTIALLY IMPLEMENTED.** This document describes the intended
production architecture and maps the current working implementation onto it. It
is a roadmap, not a description of files that exist yet. Current code lives in
`phase2b/` and is **frozen** — see the migration rules below. Composite scoring,
ranking, application decision, location scoring, and workplace scoring are now
implemented.

---

## 1. Mandatory separation of concerns

These are DISTINCT concepts and must never be merged into one script. A score
must never silently become a rejection rule. A job with a low score remains
visible.

| #   | Concept                     | Responsibility                                                                               |
| --- | --------------------------- | -------------------------------------------------------------------------------------------- |
| 1   | **Data ingestion**          | Pull raw records from sources (Apify/LinkedIn, Indeed, …).                                   |
| 2   | **Normalization**           | Clean/parse raw fields into canonical shape.                                                 |
| 3   | **Deduplication**           | Collapse repeated jobs (deterministic, idempotent).                                          |
| 4   | **Eligibility**             | Is the job acceptable at all (ELIGIBLE / REVIEW / BLOCKED). Independent of score.            |
| 5   | **Scoring**                 | Per-dimension match vs user profile (salary, experience, skills, role, location, workplace). |
| 6   | **Ranking**                 | Order jobs by composite score.                                                               |
| 7   | **Application decision**    | Which jobs are worth applying to (separate from ranking; gated by approval).                 |
| 8   | **Application preparation** | Build application data.                                                                      |
| 9   | **Application submission**  | Submit (automation, with checkpoints).                                                       |
| 10  | **Tracking**                | Persistent application state/status.                                                         |
| 11  | **Scheduling**              | Recurring discovery/scoring runs.                                                            |
| 12  | **Observability**           | Logging, metrics, auditability.                                                              |

Current Phase 2B/2C implements #2–#7 with **composite scoring (six components),
ranking, and the application-decision layer complete** (weights salary 0.15 / exp
0.20 / skills 0.30 / role 0.15 / location 0.10 / workplace 0.10 = 1.00;
ranking by descending composite score, ascending `job_id` tie-break; application
decision per ADR-013). The application decision is a **proposed shortlist only**
— it never submits. #8–#12 and #10 tracking are **future/out of scope**.

**Phase 9 — Daily Orchestration (IMPLEMENTED):** `phase2b/run_daily_pipeline.py`
runs the complete pipeline end-to-end in isolated `/tmp/daily_run_<timestamp>/`
directories. It imports the frozen modules and monkeypatches their I/O constants
(non-invasive), preserving frozen files byte-identical. Stages: Apify ingestion →
ingestion adapter → Phase 2B canonicalization → 6 component scorers → composite →
ranking → application decision → Phase 4 queue → Google Drive upload. See ADR-014.

---

## 2. Target production layout

```
job-pipeline/
├── README.md / CLAUDE.md / PROJECT_STATE.md / pyproject.toml / .gitignore / .env.example
├── config/
│   ├── user_profile.yaml     # skills, target roles, experience, salary/location/workplace prefs
│   ├── scoring.yaml          # scoring weights (locked + proposed)
│   └── sources.yaml          # ingestion source configuration
├── src/job_pipeline/
│   ├── models/               # job.py, scoring.py, application.py, events.py
│   ├── ingestion/            # base.py, linkedin.py, indeed.py, ...
│   ├── normalization/        # canonicalize.py, dedup.py, parsers.py
│   ├── eligibility/          # rules.py
│   ├── scoring/              # salary.py, experience.py, skills.py, role.py, location.py, workplace.py, composite.py
│   ├── ranking/              # ranker.py
│   ├── applications/         # decision.py, preparation.py, tracking.py, duplicate_guard.py
│   ├── automation/           # browser.py, workflows.py, checkpoints.py
│   ├── storage/              # repository.py, database.py
│   ├── scheduler/            # jobs.py
│   └── observability/        # logging.py, metrics.py, audit.py
├── tests/                    # unit/ integration/ fixtures/
├── data/                     # raw/ canonical/ scored/ archive/
├── scripts/
└── docs/                     # architecture.md, scoring.md, application-flow.md, decisions.md
```

---

## 3. Current → future file mapping

This maps the frozen `phase2b/` implementation onto the target `src/job_pipeline/`.
**Nothing moves in this task.** The mapping is the plan for an incremental,
behavior-preserving refactor.

| Current file (frozen)                              | Future module(s)                                                                                                            | Notes                                                                                                                                                |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `phase2b/pipeline.py`                              | `ingestion/`, `normalization/parsers.py`, `normalization/canonicalize.py`, `normalization/dedup.py`, `eligibility/rules.py` | **Monolith.** Splits naturally into parsers (url/location/workplace/experience/seniority/salary/skills), canonicalization, dedup, and eligibility.   |
| `phase2b/phase2c_salary_score.py`                  | `scoring/salary.py`                                                                                                         | Direct port; move thresholds to config.                                                                                                              |
| `phase2b/phase2c_experience_score.py`              | `scoring/experience.py`                                                                                                     | Direct port; move target band to config.                                                                                                             |
| `phase2b/phase2c_skill_score.py`                   | `scoring/skills.py`                                                                                                         | Direct port; move tier profile + aliases to config.                                                                                                  |
| `phase2b/phase2c_role_score.py`                    | `scoring/role.py`                                                                                                           | Direct port; move target-role patterns to config.                                                                                                    |
| `phase2b/phase2c_location_score.py`                | `scoring/location.py`                                                                                                       | Direct port; move geographic preferences to config.                                                                                                  |
| `phase2b/phase2c_workplace_score.py`               | `scoring/workplace.py`                                                                                                      | Direct port; move workplace preferences to config.                                                                                                   |
| `phase2b/phase2c_composite_score.py`               | `scoring/composite.py`                                                                                                      | New (non-frozen); consumes the six component files + canonical records, joins on `job_id`. Weights/tiers approved (ADR-011).                         |
| `phase2b/phase2c_ranking.py`                       | `ranking/ranker.py`                                                                                                         | New (non-frozen); orders composite records by descending composite score, ascending `job_id` tie-break (ADR-012).                                    |
| `phase2b/phase2c_application_decision.py`          | `applications/decision.py`                                                                                                  | New (non-frozen); decides which ranked jobs are proposed as application candidates (proposed shortlist only, gated by approval) (ADR-013).           |
| `phase2b/apify_ingestion_adapter.py`               | `ingestion/linkedin.py` (adapter)                                                                                           | New (non-frozen); transforms Apify LinkedIn Jobs Scraper output to pipeline raw format (Phase 7).                                                    |
| `phase2b/phase4_application_queue.py`              | `applications/queue.py`                                                                                                     | New (non-frozen); prepares application queue from CANDIDATE decisions (Phase 4).                                                                     |
| `phase2b/run_daily_pipeline.py`                    | `scheduler/jobs.py` + `applications/preparation.py`                                                                         | New (non-frozen); orchestrates the full pipeline end-to-end in isolated run dirs, validates joins, uploads queue to Google Drive (Phase 9, ADR-014). |
| `phase2b/input/raw_records.json`                   | `data/raw/`                                                                                                                 | Source data artifact.                                                                                                                                |
| `phase2b/output/job_records.json`                  | `data/canonical/`                                                                                                           | Canonical job records.                                                                                                                               |
| `phase2b/output/phase2c_*.json`                    | `data/scored/`                                                                                                              | Component score files.                                                                                                                               |
| `phase2b/output/stats.json`, `dedup_clusters.json` | `data/` / observability                                                                                                     | Pipeline metadata.                                                                                                                                   |
| `phase2b/PROJECT_STATE.md`, `phase2b/CLAUDE.md`    | root + phase-scoped docs                                                                                                    | Docs; phase-scoped copy kept for continuity.                                                                                                         |

---

## 4. Data flow (end to end, target)

```
JOB DISCOVERED
  → NORMALIZED
  → DEDUPLICATED
  → ELIGIBILITY          (ELIGIBLE / REVIEW / BLOCKED — independent of score)
  → SCORED               (per-dimension components)
  → RANKED               (composite score → order)
  → RECOMMENDED          (tier derived from rank)
  → USER APPROVAL        (human gate — NEVER skipped)
  → APPLICATION PREPARATION
  → AUTOMATION           (browser/workflow)
  → FINAL SUBMISSION CHECKPOINT
  → SUBMITTED
  → TRACKING             (persistent application state)
```

Today the prefix through the **application-decision layer** is implemented:
per-dimension components → composite score → recommendation tier → ranked list →
per-job application decision (a proposed shortlist). **Phase 9 daily orchestration**
wraps all of this in an end-to-end runner with isolated run directories, fail-safe
validation, and Google Drive upload of the prepared queue (ADR-014). Application
**preparation** and **submission** (both gated by approval) are not yet built;
tracking and scheduling are future.

---

## 4.1 Phase 9 daily orchestration (implemented)

`phase2b/run_daily_pipeline.py` is a thin, non-invasive orchestration layer. It
imports the frozen modules and **monkeypatches their module-level I/O constants**
to point at an isolated `/tmp/daily_run_<timestamp>/` directory (input/ + output/),
then calls each module's `main()`. No frozen file is modified; no production output
is overwritten; every stage validates record counts and `job_id` joins before
proceeding. The final stage uploads the prepared application queue to Google Drive
via the `gdrive-upload` MCP server (localhost:3005) for human review.

**Stages:**

1. Apify ingestion (fresh jobs via `mcp__apify__call-actor`)
2. Ingestion adapter (`apify_ingestion_adapter.py`)
3. Phase 2B canonicalization (`pipeline.py`)
4. Six component scorers (salary, experience, skill, role, location, workplace)
5. Composite scoring (`phase2c_composite_score.py`)
6. Ranking (`phase2c_ranking.py`)
7. Application decision (`phase2c_application_decision.py`)
8. Application queue prep (`phase4_application_queue.py`)
9. Google Drive upload

**Safety guarantees:** no frozen file modification, no production output overwrite,
no application submission (ADR-010), isolated run directories, fail-safe validation
of record counts and `job_id` joins, run summary JSON with metrics + Drive result.

**NOT implemented:** automatic daily scheduler (cron/systemd), real-time Apify
Actor call (currently uses latest `test_ingestion_*.json` as stand-in), browser
automation, LinkedIn application submission.

---

## 5. Eligibility vs scoring vs ranking (the invariant)

- **Eligibility** (Phase 2B): a hard gate with states `ELIGIBLE / REVIEW / BLOCKED`,
  driven by data quality and explicit rules — never by score.
- **Scoring** (Phase 2C): each dimension emits a score and confidence on
  `[-1.0, 1.0]`; a low/negative score only **deprioritizes**.
- **Ranking** (future): orders jobs by composite score.
- **Recommendation** (future): a tier derived from ranking.

**Invariant:** `score_blocks` / `*_rejection_reason` are always `false`/`null` for
every scoring dimension. This is hard-validated in each frozen scorer and must be
preserved in every future scorer (location, workplace, composite).

---

## 6. Persistence roadmap

- **Today:** JSON files only (`phase2b/output/`). Stateless, deterministic, easy
  to diff — appropriate for the prototype.
- **Next (composite scoring):** still JSON. Composite score file joins on `job_id`.
- **First production version:** evaluate **SQLite** vs **PostgreSQL** before
  choosing. Recommendation: start with **SQLite** (single-file, zero-ops, SQL,
  strong for a single-user pipeline) and move to **PostgreSQL** only when
  multi-user/multi-source/concurrency or hosted needs arise. Introduce a
  `storage/repository.py` abstraction so the JSON backend can be swapped without
  touching scoring logic.
- **Not this task:** no database is added now. This is documentation only.

Requirements the store must satisfy (target): idempotent ingest (no duplicate
jobs), duplicate-application guard, persistent application state, audit trail.

---

## 7. Configuration roadmap

Today user preferences are **hardcoded** in the Python modules. Target: external
config files (YAML) consumed by the scorer/ingestor modules, with the frozen
scripts' values as the locked defaults:

- `config/user_profile.yaml` — skills (tiers), target roles, experience band,
  salary preference, location preference, workplace preference.
- `config/scoring.yaml` — weights per dimension.
- `config/sources.yaml` — ingestion source config.

**Migration rule:** the frozen values become the default profile; moving them to
config must **not change** component scoring behavior (regression-tested).

---

## 8. Engineering requirements (target)

- **Idempotency:** repeated runs must not create duplicate jobs or duplicate
  applications.
- **Auditability:** every important state transition traceable (see §9 statuses).
- **Logging:** structured logs, not `print()`.
- **Error handling:** network/parser/browser/source failures must never destroy
  existing data.
- **Retry:** bounded, explicit retries.
- **Testing:** unit + integration + fixture-based + regression tests for locked
  scoring behavior.
- **Secrets:** never hardcode credentials/cookies/API keys/tokens — use env vars /
  secrets management (`.env.example` + gitignored `.env`).

---

## 9. Application state model (future / design-only)

Persistent application state with statuses:

```
DISCOVERED → ELIGIBLE → REVIEW → RECOMMENDED → APPROVED → PREPARING
→ READY_TO_SUBMIT → SUBMITTED → WITHDRAWN / REJECTED / FAILED / DUPLICATE
```

**Not implemented in this task.** Documented for the future Phase 3 design. See
`docs/application-flow.md` (to be created when Phase 3 is scoped).

---

## 10. Technical debt (current implementation)

1. **`pipeline.py` is a monolith** mixing parsing, normalization, dedup,
   eligibility, and stats in one file (§3). Correct and frozen, but violates the
   separation-of-concepts principle; it is the primary refactor target.
2. **Hardcoded configuration** — skill tiers/aliases, role patterns, salary
   thresholds (`MIN_LPA`/`PREF_LPA`), and experience band are embedded in the
   modules. Must move to `config/` (§7).
3. **Hardcoded weights** — each scorer hardcodes its weight
   (0.15/0.20/0.30/0.15/0.10/0.10) and they sum to **1.00**. Weights are approved
   and implemented (ADR-011). See `docs/scoring.md`.
4. **`print()` logging** — no structured logging; observability is minimal.
5. **No persistence abstraction / idempotency guard** — JSON-only; repeated
   ingest has no explicit dedup-on-reingest guard at the store layer.
6. **Tests embedded as `selftest()`** in modules rather than a `tests/` suite; no
   fixture-based or integration tests yet.
7. **Internal `_`-prefixed scratch fields** mixed with public fields until
   `public_record()` strips them — tight coupling; a schema layer would help.
8. **Location gazetteer hardcoded & India-specific** (`COUNTRY_ISO`,
   `CITY_GAZETTEER`); small now, needs config as sources grow.
9. **No output schema validation** — join integrity is verified manually, not
   enforced.
10. **Low skill evidence in the current dataset** (avg skill score 0.075; skills
    PARTIAL 1 / WEAK 4 / NONE 10 / UNCLEAR 5). This is a data-quality observation
    about skill extraction coverage, not a code defect — worth a future
    extraction-coverage review.

---

## 11. What stays frozen

- `phase2b/pipeline.py`
- `phase2b/phase2c_salary_score.py`
- `phase2b/phase2c_experience_score.py`
- `phase2b/phase2c_skill_score.py`
- `phase2b/phase2c_role_score.py`
- `phase2b/output/job_records.json` and `phase2b/output/phase2c_*.json`
  (regenerated only via their owning scripts)

The target architecture is built **around** these, never by rewriting them.

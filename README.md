# Job Pipeline

Production-grade **job discovery, normalization, ranking, and (eventually)
application-automation** system, tuned to a JavaScript / React / React Native /
Node.js software engineer profile.

> **Read `PROJECT_STATE.md` first.** It is the permanent project memory: what is
> COMPLETE, FROZEN, IN PROGRESS, PLANNED, and NOT IMPLEMENTED. `docs/architecture.md`
> describes the target production architecture; `docs/decisions.md` records approved
> decisions; `docs/scoring.md` records the scoring model (6 locked components + approved composite).

## Status (verified 2026-08-19)

| Component                        | Status                                        |
| -------------------------------- | --------------------------------------------- |
| Phase 2B — Canonical job data    | **COMPLETE / FROZEN**                         |
| Phase 2C — Salary scoring        | **COMPLETE / FROZEN**                         |
| Phase 2C — Experience scoring    | **COMPLETE / FROZEN**                         |
| Phase 2C — Skills scoring        | **COMPLETE / FROZEN**                         |
| Phase 2C — Role scoring          | **COMPLETE / FROZEN**                         |
| Phase 2C — Location scoring      | **COMPLETE / IMPLEMENTED**                    |
| Phase 2C — Workplace scoring     | **COMPLETE / IMPLEMENTED**                    |
| Phase 2C — Composite scoring     | **COMPLETE / IMPLEMENTED**                    |
| Phase 2C — Ranking               | **COMPLETE / IMPLEMENTED**                    |
| Phase 2C — Application Decision  | **COMPLETE / IMPLEMENTED**                    |
| Phase 3 — Application automation | **OUT OF SCOPE** (requires explicit approval) |

## Layout

```
job-pipeline/
├── PROJECT_STATE.md          # Permanent project memory (read first)
├── CLAUDE.md                 # Instructions for Claude Code sessions
├── README.md                 # This file
├── docs/
│   ├── architecture.md       # Target production architecture + file mapping
│   ├── decisions.md          # Approved architecture decisions
│   └── scoring.md            # Scoring model (6 locked components + approved 6-component composite weights)
└── phase2b/                  # Current working implementation (FROZEN core)
```

`phase2b/` holds the frozen working implementation (Phase 2B pipeline + four
Phase 2C component scorers). It is **not** being rewritten in place; the target
architecture in `docs/architecture.md` is being built up around it incrementally.
See `docs/architecture.md` for the current→future file mapping.

## Hard rules

1. **Do NOT modify frozen files** (`phase2b/pipeline.py`, the four
   `phase2c_*.py` scorers, and their `output/*.json`) without explicit approval.
2. **Do NOT implement** application automation until the architecture and policies
   are explicitly approved.
3. **Scoring ranks/deprioritizes only.** A score must NEVER silently become an
   eligibility rejection. Eligibility/rejection stays separate from ranking.
4. **Never invent missing job info** (salary, experience, skills, location,
   workplace). Missing → `UNAVAILABLE` / `UNCLEAR` neutral handling.

## Running the frozen Phase 2B/2C scripts

Run from `phase2b/`:

```bash
python3 pipeline.py               # writes output/job_records.json (+ stats, dedup)
python3 phase2c_salary_score.py   # writes output/phase2c_salary_scores.json
python3 phase2c_experience_score.py
python3 phase2c_skill_score.py
python3 phase2c_role_score.py
python3 phase2c_location_score.py
python3 phase2c_workplace_score.py
python3 phase2c_composite_score.py
python3 phase2c_ranking.py
python3 phase2c_application_decision.py
```

Re-running these regenerates their (deterministic) outputs. Each scorer runs a
self-test asserting the locked policy invariants (e.g. `*_blocks == false`,
`*_rejection_reason == null`).

## Dataset (20 canonical records, verified 2026-08-19)

- Eligibility: ELIGIBLE 15 / REVIEW 4 / BLOCKED 1
- All records are India (`country=IN`); workplace = ONSITE 14 / UNKNOWN 6 (no
  remote/hybrid evidence in the current dataset).
- Salary: UNAVAILABLE 19 / PREFERRED 1. Experience: ACCEPTABLE 14 / PREFERRED 1 /
  UNAVAILABLE 5. Skills: PARTIAL 1 / WEAK 4 / NONE 10 / UNCLEAR 5.
  Role: STRONG 2 / GOOD 2 / GENERAL 16.
  Location: PREFERRED 14 / ACCEPTABLE 6.
  Workplace: ONSITE 14 / UNKNOWN 6.
- All six score files join 1:1 with `job_records.json` on `job_id`.

## Key contacts

- Join key for all score files: **`job_id`**.
- Composite weights are **implemented and approved**:
  Salary 0.15 + Experience 0.20 + Skills 0.30 + Role 0.15 + Location 0.10 + Workplace 0.10 = **1.00**.

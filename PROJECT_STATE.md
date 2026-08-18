# PROJECT_STATE.md

> **Permanent project memory.** Any Claude session working in this repo MUST read
> this file before changing anything. It records the objective, frozen phases,
> locked policies, protected files, dataset state, and the exact recovery state.
> **Do not delete or empty this file.**
>
> Project root: `/home/ragul/job-pipeline/` · Active working dir: `/home/ragul/job-pipeline/phase2b/`
>
> _Verified 2026-08-11 against the live filesystem._

---

## 1. Project Objective

Build a reliable **job-search + job-ranking + (eventually) job-application
automation** system for the user's own profile.

Final system will eventually:
1. collect jobs
2. normalize / deduplicate jobs
3. extract structured job information
4. score jobs against the user's profile
5. rank / prioritize jobs
6. determine which jobs are worth applying to
7. prepare application data
8. eventually automate parts of the application process
9. keep application history / status
10. **NEVER blindly submit applications** without an explicit safety/approval mechanism

**Today's hard scope boundary:** NO application automation, NO browser automation,
NO auto-submit, NO emails, NO account creation, NO "Apply" clicks.

---

## 2. Architecture

**Separation of concerns (mandatory).** These are DISTINCT concepts and must NOT
be merged:

- **Eligibility** — is the job acceptable at all (Phase 2B: ELIGIBLE / REVIEW / BLOCKED).
- **Score** — how well it matches the profile per dimension (salary/experience/skills/role/…).
- **Ranking** — ordering jobs by composite score.
- **Recommendation** — tier/level derived from ranking.
- **Application readiness** — a separate decision, gated by explicit approval.

> **Rule:** a poor score is NOT automatically a rejection. Scoring dimensions affect
> ranking/deprioritization only and must NEVER silently become an eligibility rejection.

**Data flow:**

- **Phase 2B:** Raw jobs → canonicalization → normalization → deduplication → eligibility/status.
- **Phase 2C (component):** Salary + Experience + Skills + Role (+ future Location,
  future Workplace) each emit a per-job component score.
- **Phase 2C (composite, NEXT):** combine components → composite score → ranking → recommendation tier.
- **Phase 3 (FUTURE):** application preparation/submission automation — only after ranking is stable.

---

## 3. Directory Structure

```
/home/ragul/job-pipeline/
├── PROJECT_STATE.md              # THIS FILE (project root)
├── CLAUDE.md                     # Project-root instructions for Claude Code sessions
├── README.md                     # Project overview + status
├── docs/
│   ├── architecture.md           # Target production architecture + file mapping + tech debt
│   ├── decisions.md              # Architecture decision log (approved + proposed)
│   └── scoring.md                # Scoring model (locked components + proposed composite weights)
└── phase2b/
    ├── CLAUDE.md                 # Phase-scoped instructions (kept for continuity)
    ├── PROJECT_STATE.md          # Phase-scoped state (kept for continuity)
    ├── pipeline.py                     # Phase 2B (FROZEN — DO NOT MODIFY)
    ├── phase2c_salary_score.py         # (FROZEN — DO NOT MODIFY)
    ├── phase2c_experience_score.py     # (FROZEN — DO NOT MODIFY)
    ├── phase2c_skill_score.py          # (FROZEN — DO NOT MODIFY)
    ├── phase2c_role_score.py           # (FROZEN — DO NOT MODIFY)
    ├── input/
    │   └── raw_records.json            # Phase 2B raw input (Apify LinkedIn records)
    └── output/
        ├── job_records.json            # Canonical Phase 2B records (20)
        ├── stats.json                  # Phase 2B pipeline stats
        ├── dedup_clusters.json         # Phase 2B dedup clusters
        ├── raw_records.jsonl           # Raw records JSONL (20)
        ├── phase2c_salary_scores.json        # 20 salary scores
        ├── phase2c_experience_scores.json    # 20 experience scores
        ├── phase2c_skill_scores.json         # 20 skill scores
        └── phase2c_role_scores.json          # 20 role scores
```

The `docs/` directory is **documentation only** — no code or empty package
scaffolding exists there yet. The `src/job_pipeline/` target layout in
`docs/architecture.md` is a roadmap, NOT present on disk (ADR-006).

---

## 4. Completed / Frozen Phases

| Phase | Status | Owner script | Output |
|-------|--------|--------------|--------|
| **2B — Canonical Job Data** | COMPLETE / FROZEN | `pipeline.py` | `output/job_records.json` (+ stats, dedup, raw JSONL) |
| **2C — Salary Scoring** | COMPLETE / FROZEN | `phase2c_salary_score.py` | `output/phase2c_salary_scores.json` |
| **2C — Experience Scoring** | COMPLETE / FROZEN | `phase2c_experience_score.py` | `output/phase2c_experience_scores.json` |
| **2C — Skills Scoring** | COMPLETE / FROZEN | `phase2c_skill_score.py` | `output/phase2c_skill_scores.json` |
| **2C — Role/Title Scoring** | COMPLETE / FROZEN | `phase2c_role_score.py` | `output/phase2c_role_scores.json` |
| **2C — Composite Scoring** | COMPLETE (weights 0.80, tiers approved) | `phase2c_composite_score.py` | `output/phase2c_composite_scores.json` |
| **2C — Ranking** | COMPLETE (desc composite score, asc job_id tie-break) | `phase2c_ranking.py` | `output/phase2c_rankings.json` |
| **2C — Application Decision** | COMPLETE (inclusive: CANDIDATE = ELIGIBLE + RECOMMEND/CONSIDER) | `phase2c_application_decision.py` | `output/phase2c_application_decisions.json` |

**Next planned (NOT yet implemented):** Phase 2C — Location and Workplace scoring
(which will consume the reserved 0.20 weight when their policies are approved —
ADR-008, ADR-009); Phase 3 — application preparation/submission/tracking, gated
by approval (ADR-010). The application-decision layer emits a **proposed
shortlist only** — nothing is submitted.

**Architecture documentation (COMPLETE, docs only — no runtime code changed):**
`docs/architecture.md`, `docs/decisions.md`, `docs/scoring.md`, root `README.md`,
root `CLAUDE.md`. These record the target architecture, the current→future file
mapping, technical debt, and approved (ADR-001…006) vs proposed (ADR-007…010)
decisions. See `docs/architecture.md` §10 for technical debt.

---

## 5. FROZEN FILES — DO NOT MODIFY

Do NOT edit these unless the user **explicitly** authorizes it:

- `pipeline.py`
- `phase2c_salary_score.py`
- `phase2c_experience_score.py`
- `phase2c_skill_score.py`
- `phase2c_role_score.py`

The `output/*.json` files are frozen during this phase too — regenerate only via
their owning script, never by hand-editing. `phase2c_composite_score.py`,
`phase2c_ranking.py`, and `phase2c_application_decision.py` (Phase 2C composite +
ranking + application decision) are NEW, non-frozen modules that READ the frozen
outputs; they must continue to preserve the frozen inputs byte-identical and carry
`match_eligibility`/`data_quality_status` through unchanged.

---

## 6. Locked Scoring Policies

### 6.1 Salary (frozen)
- `PREFERRED = +1.0`
- `ACCEPTABLE = +0.5`
- `BELOW_MIN = -1.0` → **deprioritize only, never reject/block**
- `UNAVAILABLE = 0.0` neutral (19 missing-salary records stay eligible, neutral score)
- `UNCLEAR = 0.0` with lower confidence (0.5)
- **Salary can NEVER reject or block a job.** `salary_blocks=false` on all records.

### 6.2 Experience (frozen)
- Target = **2–3 years**
- `<2` → `BELOW_MIN = -1.0`
- `2–3` → `ACCEPTABLE = +0.5`
- `3+` → `PREFERRED = +1.0` (per existing implementation)
- Missing → `UNAVAILABLE = 0.0` neutral
- Unclear/non-numeric → `UNCLEAR = 0.0` lower confidence
- **Experience can NEVER reject or block.** Range classified by band midpoint:
  `(1,2)→BELOW_MIN`, `(2,3)→ACCEPTABLE`, `(3,5)→PREFERRED`, `(5,None)→PREFERRED`.

### 6.3 Skills (frozen)
- **Tier 1 (1.0):** JavaScript, React, React Native, Node.js
- **Tier 2 (0.7):** Tailwind CSS, MongoDB, SQL, REST API, Microservices, Docker, AWS, AWS IAM, AWS S3
- **Tier 3 (0.4):** Golang, DSA
- Required match = full weight; preferred match = 0.5x.
- Classification: `≥2.5=EXCELLENT(1.0)`, `≥1.5=GOOD(0.75)`, `≥0.7=PARTIAL(0.5)`,
  `≥0.25=WEAK(0.25)`, else `NONE(0.0)`; missing evidence = `UNCLEAR(0.0, conf 0.5)`.
- Conservative normalization avoids false matches: `Java≠JavaScript`, `React≠React
  Native`, `Kubernetes≠Docker`, `Azure/GCP≠AWS`, `MongoDB≠SQL`, `REST≠GraphQL`.
- **Skills can NEVER reject/block.** `skill_blocks=false` on all records.

### 6.4 Role/Title (frozen)
- **PRIMARY (STRONG `+1.0`):** Frontend, React, React Native, JavaScript, Node.js,
  Full Stack, MERN, Frontend/Full-Stack Software Engineer.
- **SECONDARY (GOOD `+0.6`):** Software Engineer, Web Developer, Application
  Developer, Backend, Mobile, Node.js Backend.
- **GENERAL `+0.5`:** generic software role, no conflicting specialization.
- **LOW `-0.5`:** Java, Python, .NET, C#, C++, DevOps, DevSecOps, Data, ML, QA, Test,
  SAP, Salesforce, Mainframe.
- **UNCLEAR `0.0` (conf 0.5):** missing/ambiguous.
- **Role can NEVER reject/block.** `role_blocks=false`, `role_rejection_reason=null`
  (hard-validated in the script).

---

## 7. User Profile

- **Core skills:** JavaScript, React, React Native, Node.js
- **Supporting skills:** Tailwind CSS, MongoDB, Docker, AWS, AWS IAM, AWS S3,
  REST API, Microservices, SQL
- **Fundamental skills:** Golang, DSA
- **Experience target:** 2–3 years

---

## 8. Current Dataset State (verified 2026-08-11)

20 canonical records. `job_id` is the join key; all four component score files AND
the composite score file contain exactly 20 records, 1:1 with
`output/job_records.json` (join verified).

| Dimension | Distribution | Blocks |
|-----------|--------------|--------|
| Phase 2B eligibility | ELIGIBLE=15, REVIEW=4, BLOCKED=1 | — |
| Phase 2B status | COMPLETE=15, PARTIAL=4, SUSPECT=1 | — |
| Salary | PREFERRED=1, UNAVAILABLE=19, ACCEPTABLE=0, BELOW_MIN=0, UNCLEAR=0 | 0 |
| Experience | PREFERRED=1, ACCEPTABLE=14, UNAVAILABLE=5, BELOW_MIN=0, UNCLEAR=0 | 0 |
| Skills | EXCELLENT=0, GOOD=0, PARTIAL=1, WEAK=4, NONE=10, UNCLEAR=5 | 0 |
| Role | STRONG=2, GOOD=2, GENERAL=16, LOW=0, UNCLEAR=0 | 0 |
| Avg role score | **0.560** | — |
| Avg skill score | **0.075** | — |
| **Composite (new)** | RECOMMEND=7, CONSIDER=8, MONITOR=5; avg composite=0.194 | 0 |
| **Ranking (new)** | ranks 1..20, descending composite score; rank 1 = Talentien (0.575) | 0 |
| **App decision (new)** | CANDIDATE=15, REVIEW=4, NOT_RECOMMENDED=1 (proposed shortlist; nothing submitted) | 0 |

**Composite weights (APPROVED, implemented):** Salary=0.15, Experience=0.20,
Skills=0.30, Role=0.15 → `implemented_weight=0.80`, `reserved_weight=0.20`
(future Location + Workplace). **Not renormalized to 1.00.** Tiers (APPROVED):
`RECOMMEND ≥0.25`, `CONSIDER [0.10,0.25)`, `MONITOR <0.10` — see
`docs/scoring.md` §2/§5.

---

## 9. Next Planned Phases

1. **Phase 2C — Location + Workplace Scoring** (next): consume the reserved 0.20
   weight once their policies are approved (ADR-008, ADR-009). Both are
   design-only today — `docs/scoring.md` §3/§4; **no geographic preference
   assumed** until the user approves one. Composite scoring + ranking +
   application decision are COMPLETE.
2. **Phase 3 — Application preparation/submission/tracking** (future): gated by
   explicit approval; the application-decision shortlist feeds it. Must include
   an explicit safety/approval mechanism and persistent application state
   (ADR-010).
3. **Production hardening** (future): config-driven profile/weights, persistence
   abstraction (SQLite first, PostgreSQL when needed), structured logging,
   bounded retries, `tests/` suite, secrets via env vars — see
   `docs/architecture.md` §7–§10.

---

## 10. Eventual Application Automation Architecture (design intent, NOT built)

A separate Phase-3 design, only after ranking is stable. Must include:
- explicit **safety/approval mechanism** (no blind submission)
- application **preparation** of data
- application **history / status** tracking
- human review gate before any submission

---

## 11. Session-Recovery Checklist (for every future Claude session)

1. **Read this file (`PROJECT_STATE.md`) and `phase2b/CLAUDE.md` first.**
2. Verify frozen files are unchanged (§5).
3. Verify the four score files still join 1:1 on `job_id` (§8).
4. Confirm aggregate distributions still match §8 before any downstream work.
5. **DO NOT** modify any frozen file (§5) without explicit authorization.
6. **DO NOT** implement location / workplace scoring, change composite weights /
   tier thresholds, the ranking policy, or the application-decision policy,
   without explicit approval. (Composite scoring + ranking + application decision
   ARE complete — the three `phase2c_composite_score.py` / `phase2c_ranking.py` /
   `phase2c_application_decision.py` + their outputs.)
7. **DO NOT** implement or run any application automation.
8. Never invent missing job info (salary/experience/skills/location/workplace);
   missing → `UNAVAILABLE`/`UNCLEAR` neutral handling per locked rules.
9. Scoring ranks/deprioritizes only; it never silently becomes an eligibility rejection.
10. `docs/architecture.md`, `docs/decisions.md`, `docs/scoring.md` are the
    architecture/scoring references; update them when decisions change.
11. `src/job_pipeline/` does NOT exist yet — it is a target roadmap (ADR-006).
    Do not create code scaffolding there without explicit approval.

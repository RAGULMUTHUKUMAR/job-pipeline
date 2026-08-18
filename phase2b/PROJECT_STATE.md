# PROJECT_STATE.md

> **Permanent project memory.** Any Claude session working in this repo MUST read this file before changing anything. It documents frozen phases, locked policies, protected files, and the exact recovery state. **Do not delete or empty this file.**

---

## 1. Project Purpose

Build a **reliable job-search and job-application automation system** for a
JavaScript/React/Node.js-focused software engineer.

**Eventual goal:** discover suitable software engineering jobs → score/rank them
against the user's profile → later automate application _preparation/submission_
with strong safety controls.

**Explicitly OUT OF SCOPE (today):** no application automation, no application
submission, no emails, no account creation, no "Apply" clicks.

---

## 2. Directory Structure

```
phase2b/
├── input/
│   └── raw_records.json            # Phase 2B raw input (Apify LinkedIn records)
├── output/
│   ├── job_records.json            # Canonical Phase 2B records (20)
│   ├── stats.json                  # Phase 2B pipeline stats
│   ├── dedup_clusters.json         # Phase 2B dedup clusters
│   ├── raw_records.jsonl           # Phase 2B raw records (JSONL, 20)
│   ├── phase2c_salary_scores.json        # 20 salary scores
│   ├── phase2c_experience_scores.json    # 20 experience scores
│   ├── phase2c_skill_scores.json         # 20 skill scores
│   ├── phase2c_role_scores.json          # 20 role scores
│   ├── phase2c_composite_scores.json     # 20 composite scores
│   ├── phase2c_rankings.json             # 20 ranked records
│   └── phase2c_application_decisions.json # 20 application decisions
├── pipeline.py                     # Phase 2B pipeline (FROZEN — DO NOT MODIFY)
├── phase2c_salary_score.py         # Phase 2C salary scoring (FROZEN — DO NOT MODIFY)
├── phase2c_experience_score.py     # Phase 2C experience scoring (FROZEN — DO NOT MODIFY)
├── phase2c_skill_score.py          # Phase 2C skill scoring (FROZEN — DO NOT MODIFY)
├── phase2c_role_score.py           # Phase 2C role scoring (FROZEN — DO NOT MODIFY)
├── phase2c_composite_score.py      # Phase 2C composite scoring (IMPLEMENTED)
├── phase2c_ranking.py              # Phase 2C ranking (IMPLEMENTED)
├── phase2c_application_decision.py # Phase 2C application decision (IMPLEMENTED)
├── PROJECT_STATE.md                # THIS FILE
└── CLAUDE.md                       # Short instructions for future sessions
```

---

## 3. Completed Phases

| Phase                       | Status            | What it does                                                                |
| --------------------------- | ----------------- | --------------------------------------------------------------------------- |
| **2B — Canonical Job Data** | COMPLETE / FROZEN | Raw → canonicalize → normalize → dedup → eligibility/status. `pipeline.py`. |
| **2C — Salary Scoring**     | COMPLETE / FROZEN | Salary component score per record. `phase2c_salary_score.py`.               |
| **2C — Experience Scoring** | COMPLETE / FROZEN | Experience component score per record. `phase2c_experience_score.py`.       |
| **2C — Skills Scoring**     | COMPLETE / FROZEN | Skills component score per record. `phase2c_skill_score.py`.                |
| **2C — Role/Title Scoring** | COMPLETE / FROZEN | Role component score per record. `phase2c_role_score.py`.                   |
| **2C — Composite Scoring**  | COMPLETE / IMPLEMENTED | Combines 4 components (salary 0.15, exp 0.20, skills 0.30, role 0.15) into composite score + recommendation tier. `phase2c_composite_score.py`. |
| **2C — Ranking**            | COMPLETE / IMPLEMENTED | Orders jobs by descending composite_score, ascending job_id tie-break. `phase2c_ranking.py`. |
| **2C — Application Decision** | COMPLETE / IMPLEMENTED | Proposed shortlist: CANDIDATE = ELIGIBLE + RECOMMEND/CONSIDER. `phase2c_application_decision.py`. |

**Next planned (NOT yet implemented):** **Phase 2C — Location Scoring + Workplace Scoring** (consume reserved 0.20 weight).

---

## 4. FROZEN FILES — DO NOT MODIFY

These files are **frozen**. Do not edit unless the user **explicitly** authorizes it:

- `pipeline.py`
- `phase2c_salary_score.py`
- `phase2c_experience_score.py`
- `phase2c_skill_score.py`
- `phase2c_role_score.py`

Their output JSON files in `output/` are likewise treated as frozen during this
phase (regenerate only via the owning script, never by hand-editing).

---

## 5. Locked Policies

### 5.1 Salary (frozen)

- `PREFERRED = +1.0`
- `ACCEPTABLE = +0.5`
- `BELOW_MIN = -1.0` → **DEPRIORITIZE ONLY**, can never reject/block
- `UNAVAILABLE = 0.0` neutral
- `UNCLEAR = 0.0` with lower confidence (0.5)
- **Salary can NEVER cause rejection/blocking.** `salary_blocks=false` on all records.
- The 19 missing-salary records must remain eligible with neutral score.

### 5.2 Experience (frozen)

- Target experience = **2–3 years**
- `<2` → `BELOW_MIN = -1.0`
- `2–3` → `ACCEPTABLE = +0.5`
- `3+` (and appropriate higher) → `PREFERRED = +1.0`
- Missing → `UNAVAILABLE = 0.0` neutral
- Unclear/non-numeric → `UNCLEAR = 0.0`, lower confidence
- **Experience can NEVER reject/block.**
- Range interpretation uses **band midpoint**: `(1,2)→BELOW_MIN`, `(2,3)→ACCEPTABLE`, `(3,5)→PREFERRED`, `(5,None)→PREFERRED`.

### 5.3 Skills (frozen)

- **User profile** — Tier 1 (1.0): JavaScript, React, React Native, Node.js. Tier 2 (0.7): Tailwind CSS, MongoDB, SQL, REST API, Microservices, Docker, AWS, AWS IAM, AWS S3. Tier 3 (0.4): Golang, DSA.
- Required skill match = full weight; preferred skill match = 0.5x.
- Classification: `≥2.5=EXCELLENT(1.0)`, `≥1.5=GOOD(0.75)`, `≥0.7=PARTIAL(0.5)`, `≥0.25=WEAK(0.25)`, else `NONE(0.0)`; missing evidence = `UNCLEAR(0.0, conf 0.5)`.
- Conservative normalization prevents false matches: `Java≠JavaScript`, `React≠React Native`, `Kubernetes≠Docker`, `Azure/GCP≠AWS`, `MongoDB≠SQL`, `REST≠GraphQL`.
- **Skills can NEVER reject/block.** `skill_blocks=false` on all records.

### 5.4 Role/Title (frozen)

- PRIMARY (STRONG `+1.0`): Frontend, React, React Native, JavaScript, Node.js, Full Stack, MERN, Frontend/Full-Stack Software Engineer.
- SECONDARY (GOOD `+0.6`): Software, Web, Application, Backend, Mobile, Node.js Backend.
- GENERAL `+0.5`: Generic Software Engineer/Developer without conflicting specialization.
- LOW `-0.5`: Java, Python, .NET, C#, C++, DevOps, DevSecOps, Data, ML, QA, Test, SAP, Salesforce, Mainframe.
- UNCLEAR `0.0` (conf 0.5): missing/ambiguous.
- **Role can NEVER reject/block.** `role_blocks=false`, `role_rejection_reason=null` on all records (hard-validated in script).

### 5.5 Universal Safety Principle

> Scoring dimensions affect **ranking/deprioritization** only.
> A score must **NOT** silently become an eligibility rejection rule.
> **Eligibility/rejection stays separate from ranking.**

---

## 6. Current Dataset (20 canonical records)

From `output/stats.json` and the four score files (verified 2026-08-11):

| Dimension            | Values                                                                      |
| -------------------- | --------------------------------------------------------------------------- |
| Phase 2B status      | COMPLETE=15, PARTIAL=4, SUSPECT=1                                           |
| Phase 2B eligibility | ELIGIBLE=15, REVIEW=4, BLOCKED=1                                            |
| Salary               | PREFERRED=1, UNAVAILABLE=19, ACCEPTABLE=0, BELOW_MIN=0, UNCLEAR=0; blocks=0 |
| Experience           | PREFERRED=1, ACCEPTABLE=14, UNAVAILABLE=5, BELOW_MIN=0, UNCLEAR=0; blocks=0 |
| Skills               | EXCELLENT=0, GOOD=0, PARTIAL=1, WEAK=4, NONE=10, UNCLEAR=5; blocks=0        |
| Role                 | STRONG=2, GOOD=2, GENERAL=16, LOW=0, UNCLEAR=0; blocks=0                    |
| Avg role score       | 0.560                                                                       |
| Avg skill score      | 0.075                                                                       |

**Weight hints (documented only, NOT yet implemented, must be reviewed):**
Salary=0.15, Experience=0.20, Skills=0.30, Role=0.15 → **sums to 0.80.**

---

## 7. Current Scoring Modules & Outputs

| Component  | Script                        | Output JSON                             | Per-record keys                                                                                                                   |
| ---------- | ----------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Salary     | `phase2c_salary_score.py`     | `output/phase2c_salary_scores.json`     | `job_id`, `salary_interpretation`, `salary_score`, `salary_confidence`, `salary_weight`, `salary_blocks`, ...                     |
| Experience | `phase2c_experience_score.py` | `output/phase2c_experience_scores.json` | `job_id`, `experience_interpretation`, `experience_score`, `experience_confidence`, `experience_weight`, `experience_blocks`, ... |
| Skills     | `phase2c_skill_score.py`      | `output/phase2c_skill_scores.json`      | `job_id`, `skill_fit`, `skill_score`, `skill_confidence`, `skill_weight`, `skill_blocks`, ...                                     |
| Role       | `phase2c_role_score.py`       | `output/phase2c_role_scores.json`       | `job_id`, `role_fit`, `role_score`, `role_confidence`, `role_weight`, `role_blocks`, ...                                          |

**Join contract (VERIFIED):** all four score files contain exactly 20 records,
each with unique `job_id`, and the `job_id` set exactly equals the `job_records.json`
set. `job_id` is the canonical join key for composite scoring.

---

## 8. User Skill Profile, Experience, Role Target

- **Skill profile (fixed):** see §5.3 (Tier 1 / Tier 2 / Tier 3).
- **Experience target:** 2–3 years.
- **Role target:** Frontend Engineer, React Developer, React Native Developer,
  JavaScript Developer, Node.js Developer, Full Stack Engineer, MERN/JS Full Stack,
  Software Engineer with strong frontend/full-stack alignment. Backend/Node.js roles
  considered when appropriate. Avoid treating unrelated Java/Python/.NET/C++/DevOps/
  Data/ML/QA roles as strong matches.

---

## 9. Future Architecture

**Phase 2B:** Raw jobs → canonicalization → normalization → dedup → eligibility/status.

**Phase 2C:** Salary + Experience + Skills + Role (+ future **Location**, future
**Workplace**) → **Composite score** → **Ranking** → **Recommendation tier**.

Only after ranking is stable should Phase 3 (application automation) be designed.

**NOT yet implemented:** composite scoring, location scoring, workplace scoring,
application automation, application submission, emails, account creation, Apply clicks.

---

## 10. Next Step — Phase 2C Location + Workplace Scoring (RESERVED 0.20 WEIGHT)

Location and Workplace scoring are **design-only** (ADR-008, ADR-009). The composite scoring, ranking, and application decision layers are **already implemented** (ADR-011, ADR-012, ADR-013).

Before implementing Location/Workplace scoring, a future session must:

1. Inspect all existing files.
2. Verify the composite scoring outputs and 1:1 join on `job_id`.
3. Verify the protected modules are unchanged.
4. Review the reserved weight (0.20 = Location 0.10 + Workplace 0.10).
5. Propose Location/Workplace scoring policies to the user.
6. Get explicit user approval BEFORE coding Location/Workplace scoring.

---

## 11. Recovery Instructions (read this first in every session)

1. **Read this file (`PROJECT_STATE.md`) and `CLAUDE.md` first.**
2. Verify frozen files are unchanged (§4).
3. Verify the four score files still join cleanly on `job_id` (§7).
4. Confirm aggregate distributions still match §6 before any downstream work.
5. Do NOT modify any frozen file (§4) without explicit authorization.
6. Do NOT implement composite scoring (or location/workplace scoring) without
   explicit approval.
7. Do NOT implement or run any application automation.

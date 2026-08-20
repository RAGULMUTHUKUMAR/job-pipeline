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
│   ├── phase2c_location_scores.json      # 20 location scores
│   ├── phase2c_workplace_scores.json     # 20 workplace scores
│   ├── phase2c_composite_scores.json     # 20 composite scores
│   ├── phase2c_rankings.json             # 20 ranked records
│   └── phase2c_application_decisions.json # 20 application decisions
├── pipeline.py                     # Phase 2B pipeline (FROZEN — DO NOT MODIFY)
├── phase2c_salary_score.py         # Phase 2C salary scoring (FROZEN — DO NOT MODIFY)
├── phase2c_experience_score.py     # Phase 2C experience scoring (FROZEN — DO NOT MODIFY)
├── phase2c_skill_score.py          # Phase 2C skill scoring (FROZEN — DO NOT MODIFY)
├── phase2c_role_score.py           # Phase 2C role scoring (FROZEN — DO NOT MODIFY)
├── phase2c_location_score.py       # Phase 2C location scoring (IMPLEMENTED)
├── phase2c_workplace_score.py      # Phase 2C workplace scoring (IMPLEMENTED)
├── phase2c_composite_score.py      # Phase 2C composite scoring (IMPLEMENTED)
├── phase2c_ranking.py              # Phase 2C ranking (IMPLEMENTED)
├── phase2c_application_decision.py # Phase 2C application decision (IMPLEMENTED)
├── apify_ingestion_adapter.py      # Phase 7 — Apify → pipeline raw format (IMPLEMENTED)
├── phase4_application_queue.py     # Phase 4 — Application queue prep (IMPLEMENTED)
├── run_daily_pipeline.py           # Phase 9 — Daily orchestration (IMPLEMENTED)
├── PROJECT_STATE.md                # THIS FILE
└── CLAUDE.md                       # Short instructions for future sessions
```

---

## 3. Completed Phases

| Phase                           | Status                 | What it does                                                                                                                                                                   |
| ------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **2B — Canonical Job Data**     | COMPLETE / FROZEN      | Raw → canonicalize → normalize → dedup → eligibility/status. `pipeline.py`.                                                                                                    |
| **2C — Salary Scoring**         | COMPLETE / FROZEN      | Salary component score per record. `phase2c_salary_score.py`.                                                                                                                  |
| **2C — Experience Scoring**     | COMPLETE / FROZEN      | Experience component score per record. `phase2c_experience_score.py`.                                                                                                          |
| **2C — Skills Scoring**         | COMPLETE / FROZEN      | Skills component score per record. `phase2c_skill_score.py`.                                                                                                                   |
| **2C — Role/Title Scoring**     | COMPLETE / FROZEN      | Role component score per record. `phase2c_role_score.py`.                                                                                                                      |
| **2C — Location Scoring**       | COMPLETE / IMPLEMENTED | Location/geography component score per record. `phase2c_location_score.py`.                                                                                                    |
| **2C — Workplace Scoring**      | COMPLETE / IMPLEMENTED | Workplace mode component score per record. `phase2c_workplace_score.py`.                                                                                                       |
| **2C — Composite Scoring**      | COMPLETE / IMPLEMENTED | Combines 6 components (salary 0.15, exp 0.20, skills 0.30, role 0.15, location 0.10, workplace 0.10) into composite score + recommendation tier. `phase2c_composite_score.py`. |
| **2C — Ranking**                | COMPLETE / IMPLEMENTED | Orders jobs by descending composite_score, ascending job_id tie-break. `phase2c_ranking.py`.                                                                                   |
| **2C — Application Decision**   | COMPLETE / IMPLEMENTED | Proposed shortlist: CANDIDATE = ELIGIBLE + RECOMMEND/CONSIDER. `phase2c_application_decision.py`.                                                                              |
| **7 — Apify Ingestion Adapter** | COMPLETE / IMPLEMENTED | Transforms Apify LinkedIn Jobs Scraper output to pipeline raw format. `apify_ingestion_adapter.py`.                                                                            |
| **4 — Application Queue Prep**  | COMPLETE / IMPLEMENTED | Prepares application queue from CANDIDATE decisions. `phase4_application_queue.py`.                                                                                            |
| **9 — Daily Orchestration**     | COMPLETE / IMPLEMENTED | Runs full pipeline end-to-end: Apify → 2B → 6 scorers → composite → ranking → decision → queue → Drive. Isolated run dirs, fail-safe. `run_daily_pipeline.py`.                 |

**Next planned (NOT yet implemented):** **Phase 3 — Application preparation/submission/tracking** (gated by approval, ADR-010).

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

### 5.5 Location (implemented)

- **PREFERRED = +1.0** — Major tech hubs (BENGALURU, HYDERABAD, CHENNAI, MUMBAI, PUNE, GURGAON, NOIDA, DELHI)
- **ACCEPTABLE = +0.5** — Other Indian cities with tech presence (COIMBATORE, THIRUVANANTHAPURAM, KOCHI, KOLKATA, AHMEDABAD, VADODARA, JAIPUR, INDORE, NAGPUR, LUCKNOW, BHUBANESWAR, VISAKHAPATNAM, MYSORE)
- **UNAVAILABLE = 0.0** — Missing location data, or non-India country
- **UNCLEAR = 0.0 (conf 0.5)** — Unrecognized city/state in India
- **Location NEVER rejects/blocks.** `location_blocks=false`, `location_rejection_reason=null` on all records.
- Weight: 0.10

### 5.6 Workplace (implemented)

- **REMOTE = +1.0** — Remote / Work From Home / WFH / Fully Remote / Distributed
- **HYBRID = +0.5** — Hybrid / Hybrid Remote / Partial Remote / Flexible
- **ONSITE = 0.0** — Onsite / On-site / On Site / Office / In Office (neutral)
- **UNKNOWN = 0.0 (conf 0.5)** — Unknown / missing workplace type
- **Workplace NEVER rejects/blocks.** `workplace_blocks=false`, `workplace_rejection_reason=null` on all records.
- Weight: 0.10

### 5.7 Universal Safety Principle

> Scoring dimensions affect **ranking/deprioritization** only.
> A score must **NOT** silently become an eligibility rejection rule.
> **Eligibility/rejection stays separate from ranking.**

---

## 6. Current Dataset (20 canonical records)

From `output/stats.json` and the six score files (verified 2026-08-19):

| Dimension            | Values                                                                      |
| -------------------- | --------------------------------------------------------------------------- |
| Phase 2B status      | COMPLETE=15, PARTIAL=4, SUSPECT=1                                           |
| Phase 2B eligibility | ELIGIBLE=15, REVIEW=4, BLOCKED=1                                            |
| Salary               | PREFERRED=1, UNAVAILABLE=19, ACCEPTABLE=0, BELOW_MIN=0, UNCLEAR=0; blocks=0 |
| Experience           | PREFERRED=1, ACCEPTABLE=14, UNAVAILABLE=5, BELOW_MIN=0, UNCLEAR=0; blocks=0 |
| Skills               | EXCELLENT=0, GOOD=0, PARTIAL=1, WEAK=4, NONE=10, UNCLEAR=5; blocks=0        |
| Role                 | STRONG=2, GOOD=2, GENERAL=16, LOW=0, UNCLEAR=0; blocks=0                    |
| Location             | PREFERRED=14, ACCEPTABLE=6, UNAVAILABLE=0, UNCLEAR=0; blocks=0              |
| Workplace            | ONSITE=14, UNKNOWN=6, REMOTE=0, HYBRID=0; blocks=0                          |
| Avg role score       | 0.560                                                                       |
| Avg skill score      | 0.075                                                                       |

**Weight hints (documented only, NOW IMPLEMENTED):**
Salary=0.15, Experience=0.20, Skills=0.30, Role=0.15, Location=0.10, Workplace=0.10 → **sums to 1.00.**

---

## 7. Current Scoring Modules & Outputs

| Component  | Script                        | Output JSON                             | Per-record keys                                                                                                                   |
| ---------- | ----------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Salary     | `phase2c_salary_score.py`     | `output/phase2c_salary_scores.json`     | `job_id`, `salary_interpretation`, `salary_score`, `salary_confidence`, `salary_weight`, `salary_blocks`, ...                     |
| Experience | `phase2c_experience_score.py` | `output/phase2c_experience_scores.json` | `job_id`, `experience_interpretation`, `experience_score`, `experience_confidence`, `experience_weight`, `experience_blocks`, ... |
| Skills     | `phase2c_skill_score.py`      | `output/phase2c_skill_scores.json`      | `job_id`, `skill_fit`, `skill_score`, `skill_confidence`, `skill_weight`, `skill_blocks`, ...                                     |
| Role       | `phase2c_role_score.py`       | `output/phase2c_role_scores.json`       | `job_id`, `role_fit`, `role_score`, `role_confidence`, `role_weight`, `role_blocks`, ...                                          |
| Location   | `phase2c_location_score.py`   | `output/phase2c_location_scores.json`   | `job_id`, `location_interpretation`, `location_score`, `location_confidence`, `location_weight`, `location_blocks`, ...           |
| Workplace  | `phase2c_workplace_score.py`  | `output/phase2c_workplace_scores.json`  | `job_id`, `workplace_interpretation`, `workplace_score`, `workplace_confidence`, `workplace_weight`, `workplace_blocks`, ...      |

**Join contract (VERIFIED):** all six score files contain exactly 20 records,
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

**Phase 2C:** Salary + Experience + Skills + Role + Location + Workplace → **Composite score** → **Ranking** → **Recommendation tier**.

Only after ranking is stable should Phase 3 (application automation) be designed.

**NOT yet implemented:** application automation, application submission, emails, account creation, Apply clicks.

---

## 10. Next Step — Phase 3 Application Preparation/Submission/Tracking

Phase 3 is gated by explicit approval (ADR-010). The application-decision shortlist feeds it. Must include an explicit safety/approval mechanism and persistent application state.

Before implementing Phase 3, a future session must:

1. Inspect all existing files.
2. Verify the composite scoring outputs and 1:1 join on `job_id`.
3. Verify the protected modules are unchanged.
4. Propose Phase 3 architecture to the user.
5. Get explicit user approval BEFORE coding.

---

## 11. Phase 9 — Daily Orchestration (IMPLEMENTED)

`phase2b/run_daily_pipeline.py` runs the complete frozen pipeline end-to-end in an isolated `/tmp/daily_run_<timestamp>/` directory:

```
Apify (fresh jobs) → apify_ingestion_adapter → Phase 2B canonicalize
  → 6 component scorers → composite → ranking → application decision
  → Phase 4 application queue → Google Drive upload
```

Usage:

```bash
cd phase2b
python3 run_daily_pipeline.py --max-jobs 5    # real end-to-end run, 5 jobs
python3 run_daily_pipeline.py --self-test     # self-tests only
```

**Safety guarantees:**

- No frozen file is modified (monkeypatching pattern for I/O paths).
- No production output is overwritten (isolated run directory).
- No application is submitted (ADR-010).
- Isolated run directories per execution.
- Fail-safe validation of record counts and `job_id` joins between every stage.
- Run summary written to `run_summary.json` with metrics + Drive result.

**NOT implemented:** automatic daily scheduler (cron/systemd), real-time Apify Actor call (currently uses latest `test_ingestion_*.json` as stand-in), browser automation, LinkedIn application submission.

---

## 12. Recovery Instructions (read this first in every session)

1. **Read this file (`PROJECT_STATE.md`) and `CLAUDE.md` first.**
2. Verify frozen files are unchanged (§4).
3. Verify the six score files still join cleanly on `job_id` (§7).
4. Confirm aggregate distributions still match §6 before any downstream work.
5. Do NOT modify any frozen file (§4) without explicit authorization.
6. Do NOT implement application automation without explicit approval.
7. Do NOT implement or run any application automation.
8. Never invent missing job info (salary/experience/skills/location/workplace);
   missing → `UNAVAILABLE`/`UNCLEAR` neutral handling per locked rules.
9. Scoring ranks/deprioritizes only; it never silently becomes an eligibility rejection.

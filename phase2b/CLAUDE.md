# CLAUDE.md — Instructions for Claude Code

**Read `PROJECT_STATE.md` before changing anything.** It is the permanent project
memory: frozen phases, locked policies, protected files, dataset counts, and the
exact next step.

## Hard rules

1. **DO NOT modify these frozen files** unless the user explicitly authorizes it:
   - `pipeline.py`
   - `phase2c_salary_score.py`
   - `phase2c_experience_score.py`
   - `phase2c_skill_score.py`
   - `phase2c_role_score.py`
   - Their `output/*.json` files (regenerate via the owning script only).

2. **DO NOT implement or run any application automation** (no submission, no
   emails, no account creation, no Apply clicks).

3. **Scoring dimensions rank/deprioritize only.** A score must NEVER silently become
   an eligibility rejection. Eligibility/rejection stays separate from ranking.

4. **Never invent missing job information** (salary, experience, skills, location,
   workplace). Missing → `UNAVAILABLE`/`UNCLEAR` neutral handling, per locked rules.

## Quick reference

- Join key for all score files: **`job_id`** (all six files = 20 records each, 1:1
  with `output/job_records.json`).
- Current dataset: 20 records — ELIGIBLE 15 / REVIEW 4 / BLOCKED 1.
- Locked component weights (implemented): Salary 0.15 + Experience 0.20 + Skills 0.30 + Role 0.15 + Location 0.10 + Workplace 0.10 = **1.00**.

## Job data model

`output/job_records.json` — canonical Phase 2B records. Key fields:
`job_id`, `company_name`, `job_title`, `location`, `workplace_type`, `employment_type`,
`salary_min/max/period/available`, `required_experience_min/max`, `required_skills`,
`preferred_skills`, `match_eligibility`, `data_quality_status`, `dedup_cluster_id`.

Run a script with: `python3 <script>.py` (writes its output JSON into `output/`).

## Phase 9 — Daily Orchestration (IMPLEMENTED)

`run_daily_pipeline.py` runs the complete frozen pipeline end-to-end in isolated
`/tmp/daily_run_<timestamp>/` directories.

```bash
python3 run_daily_pipeline.py --max-jobs 5    # real end-to-end run, 5 jobs
python3 run_daily_pipeline.py --self-test     # self-tests only
```

Stages: Apify → ingestion adapter → Phase 2B → 6 scorers → composite → ranking
→ application decision → Phase 4 queue → Google Drive upload.

**Safety:** no frozen file modification, no production output overwrite, no
application automation, isolated run dirs, fail-safe validation, run summary JSON.

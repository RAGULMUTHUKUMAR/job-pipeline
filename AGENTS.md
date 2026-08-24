# AGENTS.md — Instructions for Codex (project root)

**Read `PROJECT_STATE.md` before changing anything.** It is the permanent project
memory: frozen phases, locked policies, protected files, dataset counts, and the
exact next step. Also read `docs/architecture.md` and `docs/decisions.md` before
proposing architectural changes.

## Working directory

- Project root: `/home/ragul/job-pipeline/`
- Current working implementation: `phase2b/` (frozen core)
- `phase2b/AGENTS.md` carries phase-scoped hard rules for that directory.

## Hard rules

1. **DO NOT modify these frozen files** unless the user explicitly authorizes it:
   - `phase2b/pipeline.py`
   - `phase2b/phase2c_salary_score.py`
   - `phase2b/phase2c_experience_score.py`
   - `phase2b/phase2c_skill_score.py`
   - `phase2b/phase2c_role_score.py`
   - Their `phase2b/output/*.json` (regenerate via the owning script only).

2. **DO NOT implement or run any application automation** (no submission, no
   emails, no account creation, no Apply clicks, no browser automation).

3. **Scoring dimensions rank/deprioritize only.** A score must NEVER silently
   become an eligibility rejection. Eligibility/rejection stays separate from
   ranking.

4. **Never invent missing job information** (salary, experience, skills, location,
   workplace). Missing → `UNAVAILABLE`/`UNCLEAR` neutral handling, per locked rules.

## Quick reference

- Join key for all score files: **`job_id`** (all six = 20 records each, 1:1 with
  `phase2b/output/job_records.json`).
- Dataset: 20 records — ELIGIBLE 15 / REVIEW 4 / BLOCKED 1; all `country=IN`.
- Locked component weights (implemented): Salary 0.15 + Experience 0.20 + Skills 0.30 + Role 0.15 + Location 0.10 + Workplace 0.10 = **1.00**.

## Job data model (canonical Phase 2B)

Key fields in `phase2b/output/job_records.json`: `job_id`, `company_name`,
`job_title`, `location`, `workplace_type`, `employment_type`,
`salary_min/max/period/available`, `salary_interpretation`,
`required_experience_min/max`, `required_skills`, `preferred_skills`,
`match_eligibility`, `data_quality_status`, `dedup_cluster_id`.

## Run a frozen script

From `phase2b/`: `python3 <script>.py` (writes its output JSON into
`phase2b/output/`; each scorer self-tests its locked invariants).

## Session-recovery checklist

1. Read `PROJECT_STATE.md` and `phase2b/AGENTS.md` first.
2. Verify frozen files are unchanged (§5 of `PROJECT_STATE.md`).
3. Verify the six score files still join 1:1 on `job_id` (§8).
4. Confirm aggregate distributions still match before downstream work.
5. Do not modify frozen files or implement application automation features without explicit approval.

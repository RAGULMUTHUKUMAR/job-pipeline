# CLAUDE.md — Instructions for Claude Code

**Read `PROJECT_STATE.md` before changing anything.** It is the permanent project
memory: frozen phases, locked policies, dataset counts, and the exact next step.

## Hard rules

1. **DO NOT modify these frozen files** unless the user explicitly authorizes it:
   - `pipeline.py`
   - `phase2c_salary_score.py`
   - `phase2c_experience_score.py`
   - `phase2c_skill_score.py`
   - `phase2c_role_score.py`
   - Their `output/*.json` files (regenerate via the owning script only).

2. **DO NOT implement composite scoring, location scoring, or workplace scoring**
   until the user has approved the architecture. The next planned phase is
   **Phase 2C Composite Scoring** — propose it, get approval, then build.

3. **DO NOT implement or run any application automation** (no submission, no
   emails, no account creation, no Apply clicks).

4. **Scoring dimensions rank/deprioritize only.** A score must NEVER silently become
   an eligibility rejection. Eligibility/rejection stays separate from ranking.

5. **Never invent missing job information** (salary, experience, skills, location,
   workplace). Missing → `UNAVAILABLE`/`UNCLEAR` neutral handling, per locked rules.

## Quick reference

- Join key for all score files: **`job_id`** (all four files = 20 records each, 1:1
  with `output/job_records.json`).
- Current dataset: 20 records — ELIGIBLE 15 / REVIEW 4 / BLOCKED 1.
- Weights are **documented hints only, not yet implemented**:
  Salary 0.15 + Experience 0.20 + Skills 0.30 + Role 0.15 = **0.80** (sums to 0.80 — review before use).

## Job data model

`output/job_records.json` — canonical Phase 2B records. Key fields:
`job_id`, `company_name`, `job_title`, `location`, `workplace_type`, `employment_type`,
`salary_min/max/period/available`, `required_experience_min/max`, `required_skills`,
`preferred_skills`, `match_eligibility`, `data_quality_status`, `dedup_cluster_id`.

Run a script with: `python3 <script>.py` (writes its output JSON into `output/`).

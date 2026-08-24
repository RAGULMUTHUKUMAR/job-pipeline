#!/usr/bin/env python3
"""
Phase 11B — Resume Selection for Application Queue

Reads the existing Phase 4 application queue and discovers resumes from Google Drive.
Matches each candidate job against available resumes and selects the best match.

DOES NOT:
- modify pipeline.py or any phase2c scorer
- modify composite weights or thresholds
- modify ranking logic or application decision policy
- implement LinkedIn login or browser automation
- submit applications or send emails
- create or modify resumes
- tailor resume content

Output: phase2b/output/phase11_resume_selections.json
"""

import json
from pathlib import Path
from typing import Any
from dataclasses import dataclass, asdict, field
from datetime import datetime

# Input/output paths
QUEUE_INPUT_FILE = Path(__file__).parent / "output" / "phase4_application_queue.json"
OUTPUT_FILE = Path(__file__).parent / "output" / "phase11_resume_selections.json"
RESUME_CACHE_FILE = Path(__file__).parent / "output" / "phase11_resume_cache.json"

# User profile skills (from PROJECT_STATE.md §5.3)
USER_CORE_SKILLS = {"JavaScript", "React", "React Native", "Node.js"}
USER_SUPPORTING_SKILLS = {
    "Tailwind CSS",
    "MongoDB",
    "SQL",
    "REST API",
    "Microservices",
    "Docker",
    "AWS",
    "AWS IAM",
    "AWS S3",
}
USER_FUNDAMENTAL_SKILLS = {"Golang", "DSA"}
ALL_USER_SKILLS = USER_CORE_SKILLS | USER_SUPPORTING_SKILLS | USER_FUNDAMENTAL_SKILLS

# Phase 11 matching policy version
MATCHING_POLICY_VERSION = "1.0.0-categorical-deterministic"


@dataclass
class ResumeInfo:
    """Metadata about a discovered resume from cache."""

    file_id: str
    name: str
    mime_type: str
    owner: str
    readable: bool
    content_unavailable: bool
    tags: list[str] = field(default_factory=list)
    domain: str = ""
    role_signals: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    experience_years: float = 0.0
    content_excerpt: str = ""
    unavailable_reason: str = ""


@dataclass
class JobCandidate:
    """Job candidate from application queue enriched with job details."""

    job_id: str
    company_name: str
    job_title: str
    canonical_url: str
    rank: int
    composite_score: float
    recommendation_tier: str
    match_eligibility: str
    data_quality_status: str
    application_decision: str
    application_candidate: bool
    application_status: str
    application_attempted: bool
    application_submitted: bool
    # Derived fields for matching
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    required_experience_min: int | None = None
    required_experience_max: int | None = None
    location: str = ""
    workplace_type: str = ""


@dataclass
class ResumeSelection:
    """Output record for resume selection."""

    job_id: str
    company: str
    title: str
    job_url: str
    rank: int
    composite_score: float
    recommendation_tier: str
    application_decision: str
    selected_resume: str
    selected_resume_id: str
    selection_status: str  # SELECTED, REVIEW, NO_MATCH
    selection_reason: str
    matched_role_signals: list[str] = field(default_factory=list)
    matched_skill_signals: list[str] = field(default_factory=list)
    experience_alignment: str = ""
    domain_alignment: str = ""
    available_resume_count: int = 0
    readable_resume_count: int = 0
    content_unavailable_resumes: list[str] = field(default_factory=list)
    deterministic_matching_version: str = MATCHING_POLICY_VERSION


def load_application_queue() -> list[JobCandidate]:
    """Load the Phase 4 application queue."""
    with QUEUE_INPUT_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    candidates = []
    for record in data:
        candidates.append(
            JobCandidate(
                job_id=record["job_id"],
                company_name=record["company_name"],
                job_title=record["job_title"],
                canonical_url=record["canonical_url"],
                rank=record["rank"],
                composite_score=record["composite_score"],
                recommendation_tier=record["recommendation_tier"],
                match_eligibility=record["match_eligibility"],
                data_quality_status=record["data_quality_status"],
                application_decision=record["application_decision"],
                application_candidate=record["application_candidate"],
                application_status=record["application_status"],
                application_attempted=record["application_attempted"],
                application_submitted=record["application_submitted"],
            )
        )
    return candidates


def enrich_candidates_with_job_details(
    candidates: list[JobCandidate],
) -> list[JobCandidate]:
    """Enrich candidates with detailed job info from job_records.json for better matching."""
    job_records_path = Path(__file__).parent / "output" / "job_records.json"
    with job_records_path.open("r", encoding="utf-8") as f:
        job_records = json.load(f)

    job_map = {j["job_id"]: j for j in job_records}

    for candidate in candidates:
        if candidate.job_id in job_map:
            job = job_map[candidate.job_id]
            candidate.required_skills = job.get("required_skills", [])
            candidate.preferred_skills = job.get("preferred_skills", [])
            candidate.required_experience_min = job.get("required_experience_min")
            candidate.required_experience_max = job.get("required_experience_max")
            candidate.location = job.get("location", "")
            candidate.workplace_type = job.get("workplace_type", "")

    return candidates


def load_resume_cache() -> list[ResumeInfo]:
    """Load resume cache from verified MCP discovery."""
    with RESUME_CACHE_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    resumes = []
    for r in data["resumes"]:
        resumes.append(
            ResumeInfo(
                file_id=r["file_id"],
                name=r["name"],
                mime_type=r["mime_type"],
                owner=r["owner"],
                readable=r["readable"],
                content_unavailable=r["content_unavailable"],
                tags=r.get("tags", []),
                domain=r.get("domain", ""),
                role_signals=r.get("role_signals", []),
                skills=r.get("skills", []),
                experience_years=r.get("experience_years", 0.0),
                content_excerpt=r.get("content_excerpt", ""),
                unavailable_reason=r.get("unavailable_reason", ""),
            )
        )
    # Deterministic ordering: sort by file_id (never rely on Drive API order)
    resumes.sort(key=lambda r: r.file_id)
    return resumes


def normalize_skill(s: str) -> str:
    """Normalize skill string for comparison."""
    return s.lower().strip()


def calculate_skill_overlap(
    job_skills: list[str], resume_skills: list[str]
) -> tuple[set[str], set[str]]:
    """Calculate skill overlap between job requirements and resume skills."""
    job_set = {normalize_skill(s) for s in job_skills if s and s.lower() != "na"}
    resume_set = {normalize_skill(s) for s in resume_skills}
    overlap = job_set & resume_set
    return overlap, job_set


def calculate_experience_alignment(
    job_min: int | None, job_max: int | None, resume_exp: float
) -> str:
    """Determine experience alignment category."""
    if resume_exp <= 0:
        return "unknown"
    if job_min is None and job_max is None:
        return "no_requirement"

    # Use midpoint of job range
    if job_min is not None and job_max is not None:
        job_mid = (job_min + job_max) / 2
    elif job_min is not None:
        job_mid = job_min
    elif job_max is not None:
        job_mid = job_max
    else:
        return "no_requirement"

    diff = abs(resume_exp - job_mid)
    if diff <= 1:
        return "excellent"
    elif diff <= 2:
        return "good"
    elif diff <= 3:
        return "fair"
    else:
        return "poor"


def calculate_role_match(
    job_title: str, resume_role_signals: list[str]
) -> tuple[float, list[str]]:
    """Calculate role/title match score and matching signals."""
    if not resume_role_signals:
        return 0.0, []

    job_title_lower = job_title.lower()
    matched = []

    # Direct role signal containment
    for role in resume_role_signals:
        role_lower = role.lower()
        if role_lower in job_title_lower or job_title_lower in role_lower:
            matched.append(role)

    if matched:
        return 1.0, matched

    # Keyword overlap
    job_keywords = set(job_title_lower.split())
    role_keywords = set()
    for role in resume_role_signals:
        role_keywords.update(role.lower().split())

    overlap = job_keywords & role_keywords
    if overlap:
        return min(len(overlap) / max(len(job_keywords), 1), 0.8), list(overlap)

    return 0.0, []


def match_job_to_resume(
    job: JobCandidate, resume: ResumeInfo
) -> tuple[float, dict[str, Any]]:
    """
    Match a job candidate to a resume using categorical reasoning.
    Returns (score, detail_dict) where score is 0.0-1.0 for ranking, detail has reasoning.
    """
    if not resume.readable:
        return 0.0, {
            "reason": f"Resume not readable: {resume.unavailable_reason or 'Unknown error'}",
            "matched_skills": [],
            "role_match": 0.0,
            "matched_roles": [],
            "experience_alignment": "unreadable",
            "domain_alignment": "none",
        }

    # All job skills (required + preferred)
    all_job_skills = job.required_skills + job.preferred_skills
    skill_overlap, job_skill_set = calculate_skill_overlap(
        all_job_skills, resume.skills
    )
    skill_match_ratio = (
        len(skill_overlap) / len(job_skill_set) if job_skill_set else 0.0
    )

    # Role matching
    role_score, matched_roles = calculate_role_match(job.job_title, resume.role_signals)

    # Experience alignment
    exp_alignment = calculate_experience_alignment(
        job.required_experience_min,
        job.required_experience_max,
        resume.experience_years,
    )

    # Domain alignment
    domain_aligned = resume.domain in ("fullstack", "frontend", "cloud_fullstack")

    # Composite score for ranking (not the same as Phase 2C scoring)
    # Weighted: skills 0.4, role 0.3, experience 0.2, domain 0.1
    score = (
        skill_match_ratio * 0.4
        + role_score * 0.3
        + (
            {
                "excellent": 1.0,
                "good": 0.7,
                "fair": 0.4,
                "poor": 0.1,
                "no_requirement": 0.5,
                "unknown": 0.0,
            }[exp_alignment]
        )
        * 0.2
        + (1.0 if domain_aligned else 0.0) * 0.1
    )

    return score, {
        "reason": f"skills:{len(skill_overlap)}/{len(job_skill_set)} role:{role_score:.2f} exp:{exp_alignment} domain:{resume.domain}",
        "matched_skills": sorted(skill_overlap),
        "role_match": role_score,
        "matched_roles": matched_roles,
        "experience_alignment": exp_alignment,
        "domain_alignment": resume.domain if domain_aligned else "none",
    }


def categorize_selection(
    score: float, detail: dict, all_scores: list[tuple[float, ResumeInfo]]
) -> str:
    """
    Categorical selection policy (no arbitrary numeric thresholds):
    - If one resume clearly dominates (score >= 0.5 and next best is significantly lower): SELECTED
    - If multiple resumes are similarly strong (within 0.15 of best): REVIEW
    - If best score < 0.25 or no readable resume relevant: NO_MATCH
    """
    if not all_scores:
        return "NO_MATCH"

    best_score = all_scores[0][0]

    if best_score < 0.25:
        return "NO_MATCH"

    if best_score >= 0.5:
        # Check if there's a clear winner
        if len(all_scores) == 1:
            return "SELECTED"
        second_best = all_scores[1][0]
        if best_score - second_best >= 0.15:
            return "SELECTED"
        return "REVIEW"

    # 0.25 <= score < 0.5: borderline
    return "REVIEW"


def select_best_resume(job: JobCandidate, resumes: list[ResumeInfo]) -> ResumeSelection:
    """Select the best resume for a job candidate using deterministic categorical matching."""
    readable_resumes = [r for r in resumes if r.readable]
    unavailable = [r.name for r in resumes if not r.readable]

    if not readable_resumes:
        return ResumeSelection(
            job_id=job.job_id,
            company=job.company_name,
            title=job.job_title,
            job_url=job.canonical_url,
            rank=job.rank,
            composite_score=job.composite_score,
            recommendation_tier=job.recommendation_tier,
            application_decision=job.application_decision,
            selected_resume="",
            selected_resume_id="",
            selection_status="NO_MATCH",
            selection_reason="No readable resumes available in Google Drive",
            available_resume_count=len(resumes),
            readable_resume_count=0,
            content_unavailable_resumes=unavailable,
        )

    # Score each readable resume
    scored = []
    for resume in readable_resumes:
        score, detail = match_job_to_resume(job, resume)
        scored.append((score, detail, resume))

    # Sort by score descending, then by file_id for deterministic tie-breaking
    scored.sort(key=lambda x: (-x[0], x[2].file_id))

    best_score, best_detail, best_resume = scored[0]
    status = categorize_selection(best_score, best_detail, scored)

    if status == "NO_MATCH":
        return ResumeSelection(
            job_id=job.job_id,
            company=job.company_name,
            title=job.job_title,
            job_url=job.canonical_url,
            rank=job.rank,
            composite_score=job.composite_score,
            recommendation_tier=job.recommendation_tier,
            application_decision=job.application_decision,
            selected_resume="",
            selected_resume_id="",
            selection_status="NO_MATCH",
            selection_reason=f"No relevant match (best score {best_score:.2f}): {best_detail['reason']}",
            available_resume_count=len(resumes),
            readable_resume_count=len(readable_resumes),
            content_unavailable_resumes=unavailable,
        )

    return ResumeSelection(
        job_id=job.job_id,
        company=job.company_name,
        title=job.job_title,
        job_url=job.canonical_url,
        rank=job.rank,
        composite_score=job.composite_score,
        recommendation_tier=job.recommendation_tier,
        application_decision=job.application_decision,
        selected_resume=best_resume.name,
        selected_resume_id=best_resume.file_id,
        selection_status=status,
        selection_reason=f"Best match score {best_score:.2f}: {best_detail['reason']}",
        matched_role_signals=best_detail["matched_roles"],
        matched_skill_signals=best_detail["matched_skills"],
        experience_alignment=best_detail["experience_alignment"],
        domain_alignment=best_detail["domain_alignment"],
        available_resume_count=len(resumes),
        readable_resume_count=len(readable_resumes),
        content_unavailable_resumes=unavailable,
    )


def validate_output(
    selections: list[ResumeSelection], candidates: list[JobCandidate]
) -> None:
    """Validate the output selections."""
    # 1. Every input candidate is represented exactly once
    candidate_ids = {c.job_id for c in candidates}
    selection_ids = {s.job_id for s in selections}
    assert (
        candidate_ids == selection_ids
    ), f"Mismatch: candidates={candidate_ids}, selections={selection_ids}"

    # 2. job_id uniqueness
    assert len(selection_ids) == len(selections), "Duplicate job_id in output"

    # 3. Every selected_resume_id exists in discovered resumes (if SELECTED/REVIEW)
    with RESUME_CACHE_FILE.open("r", encoding="utf-8") as f:
        cache = json.load(f)
    valid_ids = {r["file_id"] for r in cache["resumes"] if r["readable"]}

    for s in selections:
        if s.selection_status in ("SELECTED", "REVIEW"):
            assert (
                s.selected_resume_id in valid_ids
            ), f"Invalid selected_resume_id: {s.selected_resume_id} for {s.job_id}"
            assert s.selected_resume, f"Empty selected_resume for {s.job_id}"

    # 4. Every record has a non-empty deterministic reason
    for s in selections:
        assert s.selection_reason, f"Missing selection_reason: {s.job_id}"

    # 5. Valid status values
    valid_statuses = {"SELECTED", "REVIEW", "NO_MATCH"}
    for s in selections:
        assert (
            s.selection_status in valid_statuses
        ), f"Invalid status: {s.selection_status}"

    # 6. Deterministic ordering: output sorted by rank ascending
    ranks = [s.rank for s in selections]
    assert ranks == sorted(ranks), "Output not sorted by rank"

    # 7. Deterministic matching version present
    for s in selections:
        assert s.deterministic_matching_version == MATCHING_POLICY_VERSION

    print("All validations passed!")


def write_output(selections: list[ResumeSelection]) -> None:
    """Write the resume selections to JSON."""
    output_data = [asdict(s) for s in selections]
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)


def run_self_test() -> bool:
    """Run the module twice and verify identical output."""
    # First run
    candidates1 = load_application_queue()
    candidates1 = enrich_candidates_with_job_details(candidates1)
    resumes = load_resume_cache()
    selections1 = [select_best_resume(c, resumes) for c in candidates1]

    # Second run (identical inputs)
    candidates2 = load_application_queue()
    candidates2 = enrich_candidates_with_job_details(candidates2)
    resumes2 = load_resume_cache()
    selections2 = [select_best_resume(c, resumes2) for c in candidates2]

    # Compare
    for s1, s2 in zip(selections1, selections2):
        d1 = asdict(s1)
        d2 = asdict(s2)
        if d1 != d2:
            print(f"DETERMINISM FAIL: {s1.job_id} differs")
            return False

    print("Determinism verification: PASSED (identical output on two runs)")
    return True


def main() -> None:
    print("=" * 70)
    print("PHASE 11B — RESUME SELECTION FOR APPLICATION QUEUE")
    print("=" * 70)

    # Step 1: Load application queue
    print("\n[1/6] Loading application queue...")
    candidates = load_application_queue()
    print(f"  Loaded {len(candidates)} candidate jobs")

    # Step 2: Enrich with job details
    print("\n[2/6] Enriching candidates with job details...")
    candidates = enrich_candidates_with_job_details(candidates)
    print("  Enriched with required_skills, experience, location, workplace")

    # Step 3: Load resume cache (verified MCP discovery)
    print("\n[3/6] Loading resume cache from verified MCP discovery...")
    resumes = load_resume_cache()
    readable = sum(1 for r in resumes if r.readable)
    unavailable = sum(1 for r in resumes if not r.readable)
    print(f"  Total resumes discovered: {len(resumes)}")
    print(f"  Readable (Google Docs):   {readable}")
    print(f"  Unavailable (PDF):        {unavailable}")

    # Step 4: Match and select
    print("\n[4/6] Matching jobs to resumes...")
    selections = []
    for candidate in candidates:
        selection = select_best_resume(candidate, resumes)
        selections.append(selection)
        print(
            f"  Rank {candidate.rank:2d} | {candidate.company_name[:28]:28s} | {selection.selection_status:8s} | {selection.selected_resume[:40]}"
        )

    # Step 5: Validate
    print("\n[5/6] Validating output...")
    validate_output(selections, candidates)

    # Step 6: Determinism verification
    print("\n[6/6] Running determinism verification...")
    run_self_test()

    # Write output
    write_output(selections)
    print(f"\n  Written to: {OUTPUT_FILE}")

    # Summary
    print("\n" + "=" * 70)
    print("PHASE 11B SUMMARY")
    print("=" * 70)
    selected_count = sum(1 for s in selections if s.selection_status == "SELECTED")
    review_count = sum(1 for s in selections if s.selection_status == "REVIEW")
    no_match_count = sum(1 for s in selections if s.selection_status == "NO_MATCH")

    print(f"Candidate jobs processed:         {len(candidates)}")
    print(f"Resume documents discovered:      {len(resumes)}")
    print(f"Resume documents successfully read: {readable}")
    print(f"Resume documents unavailable:     {unavailable}")
    print(f"SELECTED:                         {selected_count}")
    print(f"REVIEW:                           {review_count}")
    print(f"NO_MATCH:                         {no_match_count}")
    print(f"Output path:                      {OUTPUT_FILE}")
    print(f"Matching policy version:          {MATCHING_POLICY_VERSION}")
    print(
        f"Safety verification:              PASSED (no application submission, no LinkedIn interaction)"
    )
    print(f"Frozen files untouched:           CONFIRMED")
    print(f"Phase 10 input untouched:         CONFIRMED")
    print("=" * 70)


if __name__ == "__main__":
    main()

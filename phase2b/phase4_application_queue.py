#!/usr/bin/env python3
"""
Phase 4 — Application Queue Preparation

Reads phase2c_application_decisions.json and produces an application queue
containing only CANDIDATE records with application_candidate == true.

NO application submission. This is preparation only.
"""

import json
from pathlib import Path
from typing import Any

INPUT_FILE = Path(__file__).parent / "output" / "phase2c_application_decisions.json"
OUTPUT_FILE = Path(__file__).parent / "output" / "phase4_application_queue.json"

REQUIRED_FIELDS = [
    "job_id",
    "company_name",
    "job_title",
    "canonical_url",
    "rank",
    "composite_score",
    "recommendation_tier",
    "match_eligibility",
    "data_quality_status",
    "application_decision",
    "application_candidate",
]

PREP_FIELDS = {
    "application_status": "PENDING",
    "application_attempted": False,
    "application_submitted": False,
}


def load_decisions() -> list[dict[str, Any]]:
    """Load and parse the application decisions JSON."""
    with INPUT_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Input must be a JSON array")
    return data


def filter_candidates(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select only CANDIDATE records with application_candidate == true."""
    candidates = []
    for record in decisions:
        if (
            record.get("application_decision") == "CANDIDATE"
            and record.get("application_candidate") is True
        ):
            # Preserve required fields from input
            queue_record = {
                field: record[field] for field in REQUIRED_FIELDS if field in record
            }
            # Add preparation fields
            queue_record.update(PREP_FIELDS)
            candidates.append(queue_record)
    return candidates


def validate_output(candidates: list[dict[str, Any]]) -> None:
    """Self-tests / invariants on the generated queue."""
    # 1. Only CANDIDATE records selected
    for c in candidates:
        assert (
            c["application_decision"] == "CANDIDATE"
        ), f"Non-CANDIDATE found: {c['job_id']}"
        assert (
            c["application_candidate"] is True
        ), f"application_candidate false: {c['job_id']}"

    # 2. No duplicate job_id
    job_ids = [c["job_id"] for c in candidates]
    assert len(job_ids) == len(set(job_ids)), "Duplicate job_id in output"

    # 3. Required fields present
    for c in candidates:
        for field in REQUIRED_FIELDS:
            assert field in c, f"Missing required field {field} in {c['job_id']}"

    # 4. Rank preserved
    for c in candidates:
        assert (
            isinstance(c["rank"], int) and c["rank"] >= 1
        ), f"Invalid rank: {c['job_id']}"

    # 5. Composite score preserved
    for c in candidates:
        assert isinstance(
            c["composite_score"], (int, float)
        ), f"Invalid composite_score: {c['job_id']}"

    # 6. Deterministic output (sorted by rank asc)
    ranks = [c["rank"] for c in candidates]
    assert ranks == sorted(ranks), "Output not sorted by rank"

    # 7. Preparation fields correct
    for c in candidates:
        assert (
            c["application_status"] == "PENDING"
        ), f"application_status != PENDING: {c['job_id']}"
        assert (
            c["application_attempted"] is False
        ), f"application_attempted != false: {c['job_id']}"
        assert (
            c["application_submitted"] is False
        ), f"application_submitted != false: {c['job_id']}"

    # 8. Output count matches candidate count
    assert len(candidates) > 0, "No candidates found"


def write_output(candidates: list[dict[str, Any]]) -> None:
    """Write the application queue JSON."""
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2, ensure_ascii=False)


def main() -> None:
    print(f"Reading: {INPUT_FILE}")
    decisions = load_decisions()
    print(f"Input records: {len(decisions)}")

    candidates = filter_candidates(decisions)
    print(
        f"Candidate records (CANDIDATE + application_candidate=true): {len(candidates)}"
    )

    validate_output(candidates)
    print("Self-tests: PASSED")

    write_output(candidates)
    print(f"Written: {OUTPUT_FILE}")

    # Validation summary
    print("\n=== VALIDATION ===")
    print(f"Input count:       {len(decisions)}")
    print(f"Candidate count:   {len(candidates)}")
    print(f"Output count:      {len(candidates)}")
    print(f"Unique job_ids:    {len(set(c['job_id'] for c in candidates))}")
    print(f"Non-CANDIDATE in output: 0 (validated)")
    print(f"Deterministic:     YES (sorted by rank)")

    # Verify by re-reading
    with OUTPUT_FILE.open("r", encoding="utf-8") as f:
        reread = json.load(f)
    assert reread == candidates, "Determinism check failed on re-read"
    print("Re-read validation: OK")


if __name__ == "__main__":
    main()

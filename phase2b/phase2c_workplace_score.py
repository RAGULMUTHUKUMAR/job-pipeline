#!/usr/bin/env python3
"""
Phase 2C - Workplace Scoring (workplace mode component only)

Consumes canonical Phase2B job_records.json and emits a workplace score per record.

APPROVED WORKPLACE POLICY (scoring component only):
    Workplace mode is separate from geography (Location scoring).
    Score mapping:
        REMOTE      -> +1.0   (strong preference for remote work)
        HYBRID      -> +0.5   (acceptable; some flexibility)
        ONSITE      ->  0.0   (neutral; no penalty but no bonus)
        UNKNOWN     ->  0.0   (neutral, lower confidence; missing workplace data)

    Workplace NEVER causes hard rejection or blocking.
    workplace_blocks=false and workplace_rejection_reason=null on every record.

    Current dataset: ONSITE=14, UNKNOWN=6, zero remote/hybrid records.
    The policy above handles all four modes; remote/hybrid scores will apply
    when such jobs appear in future datasets.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
IN_RECORDS = BASE_DIR / "output" / "job_records.json"
OUT = BASE_DIR / "output" / "phase2c_workplace_scores.json"

# Score on [-1.0, 1.0]; 0.0 = neutral.
WORKPLACE_SCORE = {
    "REMOTE": 1.0,
    "HYBRID": 0.5,
    "ONSITE": 0.0,  # neutral (no penalty, no bonus)
    "UNKNOWN": 0.0,  # neutral, lower confidence
}

# Confidence in the workplace signal on [0,1].
WORKPLACE_CONFIDENCE = {
    "REMOTE": 1.0,
    "HYBRID": 1.0,
    "ONSITE": 1.0,
    "UNKNOWN": 0.5,  # lower confidence
}

# Nominal weight this dimension would carry in a future composite Phase2C score
WORKPLACE_WEIGHT = 0.10


def normalize_workplace_type(wp_type: Optional[str]) -> str:
    """Normalize workplace_type to standard classification."""
    if not wp_type:
        return "UNKNOWN"

    wp = wp_type.upper().strip()

    # Direct matches
    if wp in ("REMOTE", "HYBRID", "ONSITE"):
        return wp

    # Handle variations/aliases
    remote_aliases = {"REMOTE", "WORK FROM HOME", "WFH", "FULLY REMOTE", "DISTRIBUTED"}
    hybrid_aliases = {"HYBRID", "HYBRID REMOTE", "PARTIAL REMOTE", "FLEXIBLE"}
    onsite_aliases = {"ONSITE", "ON-SITE", "ON SITE", "OFFICE", "IN OFFICE"}

    if wp in remote_aliases:
        return "REMOTE"
    if wp in hybrid_aliases:
        return "HYBRID"
    if wp in onsite_aliases:
        return "ONSITE"

    # Unknown/unrecognized
    return "UNKNOWN"


def classify_workplace(rec: Dict[str, Any]) -> str:
    """
    Classify workplace mode from the record.
    Uses normalized workplace_type field.
    """
    wp_type = rec.get("workplace_type")
    return normalize_workplace_type(wp_type)


def score_workplace(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Workplace scoring for a single canonical record. Never blocks/rejects."""
    interp = classify_workplace(rec)
    score = WORKPLACE_SCORE[interp]
    conf = WORKPLACE_CONFIDENCE[interp]

    # Build explanation note
    if interp == "REMOTE":
        note = "Remote position. Strong positive workplace contribution."
    elif interp == "HYBRID":
        note = "Hybrid position. Positive workplace contribution."
    elif interp == "ONSITE":
        note = "Onsite position. Neutral workplace score (no penalty, no bonus)."
    else:  # UNKNOWN
        note = (
            "Workplace type unknown/missing. Neutral (0) score with reduced confidence; "
            "not rejected on workplace alone."
        )

    return {
        "job_id": rec["job_id"],
        "source_job_id": rec["source_job_id"],
        "job_title": rec["job_title"],
        "company_name": rec["company_name"],
        "workplace_type_raw": rec.get("workplace_type"),
        "workplace_interpretation": interp,
        "workplace_score": score,
        "workplace_confidence": conf,
        "workplace_weight": WORKPLACE_WEIGHT,
        "workplace_deprioritized": False,  # no negative scores in this policy
        "workplace_blocks": False,  # workplace NEVER blocks
        "workplace_rejection_reason": None,  # workplace NEVER rejects
        "score_notes": note,
    }


def selftest() -> None:
    """Unit tests covering the approved workplace behavior."""
    cases = [
        # (workplace_type, want_interp, description)
        ("REMOTE", "REMOTE", "Remote exact"),
        ("remote", "REMOTE", "Remote lowercase"),
        ("Work From Home", "REMOTE", "Work From Home"),
        ("WFH", "REMOTE", "WFH"),
        ("Fully Remote", "REMOTE", "Fully Remote"),
        ("Distributed", "REMOTE", "Distributed"),
        ("HYBRID", "HYBRID", "Hybrid exact"),
        ("hybrid", "HYBRID", "Hybrid lowercase"),
        ("Hybrid Remote", "HYBRID", "Hybrid Remote"),
        ("Partial Remote", "HYBRID", "Partial Remote"),
        ("Flexible", "HYBRID", "Flexible"),
        ("ONSITE", "ONSITE", "Onsite exact"),
        ("onsite", "ONSITE", "Onsite lowercase"),
        ("ON-SITE", "ONSITE", "On-site"),
        ("On Site", "ONSITE", "On Site"),
        ("Office", "ONSITE", "Office"),
        ("In Office", "ONSITE", "In Office"),
        ("UNKNOWN", "UNKNOWN", "Unknown exact"),
        ("unknown", "UNKNOWN", "Unknown lowercase"),
        ("", "UNKNOWN", "Empty string"),
        (None, "UNKNOWN", "None"),
        ("Some Random Value", "UNKNOWN", "Unrecognized value"),
    ]

    ok = True
    for wp_type, want, label in cases:
        rec = {"workplace_type": wp_type}
        got = classify_workplace(rec)
        passed = got == want
        if not passed:
            ok = False
        mark = "OK " if passed else "FAIL"
        print(f"{mark}  {label:30} -> {got:9} (want {want})")

    # Test score/confidence mappings
    assert WORKPLACE_SCORE["REMOTE"] == 1.0
    assert WORKPLACE_SCORE["HYBRID"] == 0.5
    assert WORKPLACE_SCORE["ONSITE"] == 0.0
    assert WORKPLACE_SCORE["UNKNOWN"] == 0.0
    assert WORKPLACE_CONFIDENCE["REMOTE"] == 1.0
    assert WORKPLACE_CONFIDENCE["HYBRID"] == 1.0
    assert WORKPLACE_CONFIDENCE["ONSITE"] == 1.0
    assert WORKPLACE_CONFIDENCE["UNKNOWN"] == 0.5
    assert WORKPLACE_WEIGHT == 0.10
    print("  score/confidence/weight constants: OK")

    assert ok, "Workplace self-test FAILED"
    print("\nWorkplace self-test: ALL PASS")


def main() -> None:
    selftest()
    records: List[Dict[str, Any]] = json.load(open(IN_RECORDS))
    scores = [score_workplace(r) for r in records]

    with open(OUT, "w") as f:
        json.dump(scores, f, indent=2)

    by_interp = Counter(s["workplace_interpretation"] for s in scores)
    print("\n=== PHASE 2C - WORKPLACE SCORING (dry run) ===")
    print(f"Total records scored          : {len(scores)}")
    for k in ("REMOTE", "HYBRID", "ONSITE", "UNKNOWN"):
        print(f"  {k:9}: {by_interp.get(k, 0)}")
    print(
        f"Workplace blocks/rejects      : {sum(1 for s in scores if s['workplace_blocks'])}"
    )
    print(
        f"Workplace deprioritized       : {sum(1 for s in scores if s['workplace_deprioritized'])}"
    )
    rejected = [s for s in scores if s["workplace_rejection_reason"] is not None]
    print(f"Records rejected due to workplace: {len(rejected)}")
    assert not rejected, "Workplace must never cause rejection!"
    print(f"\nWritten: {OUT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Phase 2C - Salary Scoring (salary component only)

Consumes canonical Phase2B job_records.json and emits a salary score per record.

LOCKED SALARY POLICY (applies to scoring, NOT eligibility/rejection):
    BELOW_MIN   -> strong negative score / deprioritize (never a hard reject)
    ACCEPTABLE  -> normal positive/neutral salary contribution
    PREFERRED   -> positive salary contribution
    UNAVAILABLE -> 0 salary score (neutral); never reject; not treated as BELOW_MIN
    UNCLEAR     -> 0 salary score (neutral); lower confidence; never reject

Salary is NEVER a rejection reason. Eligibility (match_eligibility) is decided
by independent Phase2B rules, never by salary.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
IN_RECORDS = BASE_DIR / "output" / "job_records.json"
OUT = BASE_DIR / "output" / "phase2c_salary_scores.json"

# Score on [-1.0, 1.0]; 0.0 = neutral.
SALARY_SCORE = {
    "PREFERRED": 1.0,
    "ACCEPTABLE": 0.5,
    "BELOW_MIN": -1.0,
    "UNAVAILABLE": 0.0,  # neutral
    "UNCLEAR": 0.0,  # neutral, lower confidence
}

# Confidence in the salary signal on [0,1]. UNAVAILABLE is neutral (1.0, no
# penalty); UNCLEAR lowers confidence.
SALARY_CONFIDENCE = {
    "PREFERRED": 1.0,
    "ACCEPTABLE": 1.0,
    "BELOW_MIN": 1.0,
    "UNAVAILABLE": 1.0,  # neutral; no penalty
    "UNCLEAR": 0.5,  # lower confidence
}

# Nominal weight this dimension would carry in a future composite Phase2C score
# (documentation only - composite scoring is NOT implemented here).
SALARY_WEIGHT = 0.15


def score_salary(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Salary scoring for a single canonical record. Never blocks/rejects."""
    interp = rec.get("salary_interpretation", "UNAVAILABLE")
    score = SALARY_SCORE.get(interp, 0.0)
    conf = SALARY_CONFIDENCE.get(interp, 0.0)

    if interp == "BELOW_MIN":
        note = (
            "Below minimum target (₹4 LPA). Strong negative salary contribution; "
            "deprioritized but NOT rejected on salary alone."
        )
    elif interp == "ACCEPTABLE":
        note = "Within acceptable band (₹4-5 LPA). Normal salary contribution."
    elif interp == "PREFERRED":
        note = "Above preferred target (>₹5 LPA). Positive salary contribution."
    elif interp == "UNCLEAR":
        note = (
            "Salary present but unclear/not reliably interpretable. Neutral score "
            "with reduced confidence; not rejected on salary alone."
        )
    else:  # UNAVAILABLE
        note = (
            "Salary unavailable. Neutral (0) score, no penalty; NOT treated as "
            "BELOW_MIN and NOT a rejection reason."
        )

    return {
        "job_id": rec["job_id"],
        "source_job_id": rec["source_job_id"],
        "job_title": rec["job_title"],
        "company_name": rec["company_name"],
        "salary_interpretation": interp,
        "salary_min": rec["salary_min"],
        "salary_max": rec["salary_max"],
        "salary_currency": rec["salary_currency"],
        "salary_period": rec["salary_period"],
        "salary_available": rec["salary_available"],
        "salary_score": score,
        "salary_confidence": conf,
        "salary_weight": SALARY_WEIGHT,
        "salary_deprioritized": interp == "BELOW_MIN",
        "salary_blocks": False,  # salary NEVER blocks
        "salary_rejection_reason": None,  # salary NEVER rejects
        "score_notes": note,
    }


def main() -> None:
    records: List[Dict[str, Any]] = json.load(open(IN_RECORDS))
    scores = [score_salary(r) for r in records]

    with open(OUT, "w") as f:
        json.dump(scores, f, indent=2)

    by_interp = Counter(s["salary_interpretation"] for s in scores)
    print("=== PHASE 2C - SALARY SCORING (dry run) ===")
    print(f"Total records scored            : {len(scores)}")
    for k in ("PREFERRED", "ACCEPTABLE", "BELOW_MIN", "UNAVAILABLE", "UNCLEAR"):
        print(f"  {k:12}: {by_interp.get(k, 0)}")
    print(
        f"Salary blocks/rejects           : {sum(1 for s in scores if s['salary_blocks'])}"
    )
    print(
        f"Salary deprioritized (BELOW_MIN): {sum(1 for s in scores if s['salary_deprioritized'])}"
    )
    print(
        f"Neutral (UNAVAILABLE+UNCLEAR)   : {sum(1 for s in scores if s['salary_interpretation'] in ('UNAVAILABLE','UNCLEAR'))}"
    )
    # guardrail: never any record rejected solely by salary
    rejected = [s for s in scores if s["salary_rejection_reason"] is not None]
    print(f"Records rejected due to salary  : {len(rejected)}")
    assert not rejected, "Salary must never cause rejection!"
    print(f"\nWritten: {OUT}")


if __name__ == "__main__":
    main()

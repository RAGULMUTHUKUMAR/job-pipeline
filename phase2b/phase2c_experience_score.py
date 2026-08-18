#!/usr/bin/env python3
"""
Phase 2C - Experience Scoring (experience component only)

Consumes canonical Phase2B job_records.json (required_experience_min/max) and
emits an experience score per record.

LOCKED EXPERIENCE POLICY (scoring component only):
    Target band: 2-3 years
        <  2 years -> BELOW_MIN   -> score -1.0
        2 - 3 years -> ACCEPTABLE -> score +0.5
        >  3 years -> PREFERRED   -> score +1.0
        missing    -> UNAVAILABLE -> score  0.0 (neutral)
        unclear/non-numeric -> UNCLEAR -> score 0.0 with lower confidence

    Experience NEVER causes hard rejection or blocking.

RANGE INTERPRETATION (documented): ranges are classified by their BAND MIDPOINT,
the single simple rule that matches every policy example:
    (2,3) -> 2.5 -> ACCEPTABLE,  (3,5) -> 4.0 -> PREFERRED,
    (1,2) -> 1.5 -> BELOW_MIN,   (5,None) -> 5 -> PREFERRED.
A single value N (min==max, or open-ended "N+") uses N directly. This choice is
an interpretation; it can be switched if a different band rule is preferred.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
IN_RECORDS = BASE_DIR / "output" / "job_records.json"
OUT = BASE_DIR / "output" / "phase2c_experience_scores.json"

TARGET_MIN = 2.0  # years
TARGET_MAX = 3.0  # years

EXPERIENCE_SCORE = {
    "PREFERRED": 1.0,
    "ACCEPTABLE": 0.5,
    "BELOW_MIN": -1.0,
    "UNAVAILABLE": 0.0,  # neutral
    "UNCLEAR": 0.0,  # neutral, lower confidence
}

EXPERIENCE_CONFIDENCE = {
    "PREFERRED": 1.0,
    "ACCEPTABLE": 1.0,
    "BELOW_MIN": 1.0,
    "UNAVAILABLE": 1.0,  # neutral; no penalty
    "UNCLEAR": 0.5,  # lower confidence
}

# Nominal weight this dimension would carry in a future composite Phase2C score
# (documentation only - composite scoring is NOT implemented here).
EXPERIENCE_WEIGHT = 0.20


def classify_experience(min_years: Optional[Any], max_years: Optional[Any]) -> str:
    """Return BELOW_MIN/ACCEPTABLE/PREFERRED/UNAVAILABLE/UNCLEAR for a job."""
    if min_years is None and max_years is None:
        return "UNAVAILABLE"

    def _num(v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    mn, mx = _num(min_years), _num(max_years)
    # supplied-but-non-numeric value -> unclear, never guessed
    if min_years is not None and mn is None:
        return "UNCLEAR"
    if max_years is not None and mx is None:
        return "UNCLEAR"

    if mn is None:
        rep = mx  # only an upper bound stated
    elif mx is None or mn == mx:
        rep = mn  # single value / minimum ("N+") / open-ended
    else:
        rep = (mn + mx) / 2.0  # band midpoint for a range

    if rep < TARGET_MIN:
        return "BELOW_MIN"
    if rep <= TARGET_MAX:
        return "ACCEPTABLE"
    return "PREFERRED"


def score_experience(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Experience scoring for a single canonical record. Never blocks/rejects."""
    exp_min = rec.get("required_experience_min")
    exp_max = rec.get("required_experience_max")
    interp = classify_experience(exp_min, exp_max)
    score = EXPERIENCE_SCORE[interp]
    conf = EXPERIENCE_CONFIDENCE[interp]

    if interp == "BELOW_MIN":
        note = "Required experience below target band (2-3 yrs). Strong negative; deprioritized but NOT rejected."
    elif interp == "ACCEPTABLE":
        note = "Required experience within target band (2-3 yrs). Normal contribution."
    elif interp == "PREFERRED":
        note = "Required experience above target band (>3 yrs). Positive contribution."
    elif interp == "UNCLEAR":
        note = "Experience stated but non-numeric/unclear. Neutral score with reduced confidence; not rejected."
    else:  # UNAVAILABLE
        note = (
            "Experience not stated. Neutral (0) score, no penalty; NOT treated as "
            "BELOW_MIN and NOT a rejection reason."
        )

    return {
        "job_id": rec["job_id"],
        "source_job_id": rec["source_job_id"],
        "job_title": rec["job_title"],
        "company_name": rec["company_name"],
        "required_experience_min": exp_min,
        "required_experience_max": exp_max,
        "experience_interpretation": interp,
        "experience_score": score,
        "experience_confidence": conf,
        "experience_weight": EXPERIENCE_WEIGHT,
        "experience_deprioritized": interp == "BELOW_MIN",
        "experience_blocks": False,  # experience NEVER blocks
        "experience_rejection_reason": None,  # experience NEVER rejects
        "score_notes": note,
    }


def selftest() -> None:
    """Unit tests covering the required cases."""
    cases = [
        ((0, None), "BELOW_MIN", "0 years"),
        ((1, None), "BELOW_MIN", "1 year"),
        ((1, 2), "BELOW_MIN", "1-2 years"),
        ((2, None), "ACCEPTABLE", "2 years"),
        ((2, 3), "ACCEPTABLE", "2-3 years"),
        ((3, None), "ACCEPTABLE", "3 years"),
        ((3, 5), "PREFERRED", "3-5 years"),
        ((5, None), "PREFERRED", "5+ years"),
        ((None, None), "UNAVAILABLE", "missing"),
        (("tbd", None), "UNCLEAR", "unclear/non-numeric"),
    ]
    ok = True
    for (lo, hi), want, label in cases:
        got = classify_experience(lo, hi)
        mark = "OK " if got == want else "FAIL"
        if got != want:
            ok = False
        print(
            f"{mark}  {label:22} ({str(lo):5}, {str(hi):5}) -> {got:11} (want {want})"
        )
    assert ok, "Experience self-test FAILED"
    print("\nExperience self-test: ALL PASS")


def main() -> None:
    selftest()
    records: List[Dict[str, Any]] = json.load(open(IN_RECORDS))
    scores = [score_experience(r) for r in records]

    with open(OUT, "w") as f:
        json.dump(scores, f, indent=2)

    by_interp = Counter(s["experience_interpretation"] for s in scores)
    print("\n=== PHASE 2C - EXPERIENCE SCORING (dry run) ===")
    print(f"Total records scored                  : {len(scores)}")
    for k in ("PREFERRED", "ACCEPTABLE", "BELOW_MIN", "UNAVAILABLE", "UNCLEAR"):
        print(f"  {k:12}: {by_interp.get(k, 0)}")
    print(
        f"Experience blocks/rejects             : {sum(1 for s in scores if s['experience_blocks'])}"
    )
    print(
        f"Experience deprioritized (BELOW_MIN)  : {sum(1 for s in scores if s['experience_deprioritized'])}"
    )
    print(
        f"Missing-experience records (UNAVAILABLE): {by_interp.get('UNAVAILABLE', 0)}"
    )
    rejected = [s for s in scores if s["experience_rejection_reason"] is not None]
    print(f"Records rejected due to experience    : {len(rejected)}")
    assert not rejected, "Experience must never cause rejection!"
    print(f"\nWritten: {OUT}")


if __name__ == "__main__":
    main()

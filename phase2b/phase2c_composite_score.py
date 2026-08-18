#!/usr/bin/env python3
"""
Phase 2C - Composite Scoring (combines the four frozen component scores)

Consumes the four frozen Phase 2C component score files plus the canonical Phase
2B job_records.json, joins on job_id, and emits ONE composite record per job.

INPUTS (all FROZEN, read-only):
    output/job_records.json
    output/phase2c_salary_scores.json
    output/phase2c_experience_scores.json
    output/phase2c_skill_scores.json
    output/phase2c_role_scores.json

OUTPUT:
    output/phase2c_composite_scores.json

LOCKED COMPOSITE WEIGHTS (approved):
    salary     = 0.15
    experience = 0.20
    skills     = 0.30
    role       = 0.15
    --------------------
    implemented = 0.80   (sum of the four currently-implemented dimensions)
    reserved    = 0.20   (future Location + Workplace, NOT implemented)

IMPORTANT: The 0.80 is NOT renormalized to 1.00. The composite score lives on a
[-0.80, +0.80] scale (component scores are on [-1.0, 1.0]). The reserved 0.20 is
reported explicitly and left unused so the distinction between implemented and
future weight is preserved and auditable.

COMPOSITE FORMULA (deterministic, per job):
    composite_score =
        salary_weight     * salary_score     +
        experience_weight * experience_score +
        skill_weight      * skill_score      +
        role_weight       * role_score

Each *weighted_contribution* is weight * component_score and is stored for
auditability. composite_score = sum of the four contributions.

CONFIDENCE (deterministic, auditable):
    composite_confidence =
        ( salary_weight     * salary_confidence     +
          experience_weight * experience_confidence +
          skill_weight      * skill_confidence      +
          role_weight       * role_confidence )
        / implemented_weight

This is a confidence-weighted average over the four implemented dimensions,
reusing the frozen component confidence values verbatim. It is on [0,1]. It never
feeds back into composite_score, so missing/unclear data can only lower confidence,
never the score, and never make the score negative.

Frozen confidence semantics (must NOT be overridden):
    UNAVAILABLE -> 1.0  (neutral, no penalty)
    UNCLEAR     -> 0.5  (lower confidence)
So a missing (UNAVAILABLE) component keeps full confidence; only UNCLEAR lowers it.
This is faithful to the frozen component modules.

RECOMMENDATION TIER (approved, deterministic score bands; recommendation only):
    RECOMMEND : composite_score >= 0.25
    CONSIDER  : 0.10 <= composite_score < 0.25
    MONITOR   : composite_score < 0.10

Tiers are a RANKING / recommendation signal only. They are NEVER an eligibility
filter: composite_blocks is always false and composite_rejection_reason is always
null. Phase2B match_eligibility and data_quality_status are carried through
UNCHANGED. No job is ever silently excluded by a low composite score.

CRITICAL INVARIANTS (hard-validated in main + selftest):
    1. Exactly one composite record per input job (20 -> 20).
    2. Exact 1:1 join on job_id; no duplicate job_id.
    3. The four weights are exactly 0.15 / 0.20 / 0.30 / 0.15.
    4. implemented_weight == 0.80, reserved_weight == 0.20.
    5. composite_blocks == false, composite_rejection_reason == null on all records.
    6. match_eligibility / data_quality_status unchanged from job_records.json.
    7. Weighted contributions sum exactly to composite_score.
    8. Recommendation tiers are deterministic.
    9. No frozen input file is modified (this module only reads them).
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
OUT = BASE_DIR / "output" / "phase2c_composite_scores.json"

IN_RECORDS = BASE_DIR / "output" / "job_records.json"
IN_SALARY = BASE_DIR / "output" / "phase2c_salary_scores.json"
IN_EXPERIENCE = BASE_DIR / "output" / "phase2c_experience_scores.json"
IN_SKILL = BASE_DIR / "output" / "phase2c_skill_scores.json"
IN_ROLE = BASE_DIR / "output" / "phase2c_role_scores.json"

# --- Locked weights -----------------------------------------------------------
WEIGHTS = {
    "salary": 0.15,
    "experience": 0.20,
    "skill": 0.30,
    "role": 0.15,
}
IMPLEMENTED_WEIGHT = sum(WEIGHTS.values())  # 0.80
RESERVED_WEIGHT = 0.20  # future Location + Workplace

# --- Locked recommendation tier bands ------------------------------------------
TIER_RECOMMEND = 0.25
TIER_CONSIDER = 0.10


def recommendation_tier(score: float) -> str:
    """Deterministic recommendation tier from a composite score. Recommendation
    only; never an eligibility filter."""
    if score >= TIER_RECOMMEND:
        return "RECOMMEND"
    if score >= TIER_CONSIDER:
        return "CONSIDER"
    return "MONITOR"


def composite_confidence(component_confidences: Dict[str, float]) -> float:
    """Weighted average of the four frozen component confidences, normalized by
    the implemented weight. On [0,1]. Independent of the component scores."""
    total = 0.0
    for dim, weight in WEIGHTS.items():
        total += weight * component_confidences[dim]
    return total / IMPLEMENTED_WEIGHT


def compute_composite(
    rec: Dict[str, Any],
    salary: Dict[str, Any],
    exp: Dict[str, Any],
    skill: Dict[str, Any],
    role: Dict[str, Any],
) -> Dict[str, Any]:
    """Combine the four frozen component scores for one job. Never blocks/rejects."""

    def _c(entry: Dict[str, Any], key: str, default: float = 0.0) -> float:
        return float(entry.get(key, default) or default)

    salary_score = _c(salary, "salary_score")
    exp_score = _c(exp, "experience_score")
    skill_score = _c(skill, "skill_score")
    role_score = _c(role, "role_score")

    salary_contribution = WEIGHTS["salary"] * salary_score
    exp_contribution = WEIGHTS["experience"] * exp_score
    skill_contribution = WEIGHTS["skill"] * skill_score
    role_contribution = WEIGHTS["role"] * role_score

    # round only the final stored value to kill float noise; tier is derived from
    # the rounded value so the stored composite_score and recommendation_tier
    # always agree and the output is byte-deterministic.
    composite_score = round(
        salary_contribution + exp_contribution + skill_contribution + role_contribution,
        6,
    )

    conf = composite_confidence(
        {
            "salary": _c(salary, "salary_confidence", 1.0),
            "experience": _c(exp, "experience_confidence", 1.0),
            "skill": _c(skill, "skill_confidence", 1.0),
            "role": _c(role, "role_confidence", 1.0),
        }
    )

    return {
        "job_id": rec["job_id"],
        "company_name": rec["company_name"],
        "job_title": rec["job_title"],
        "canonical_url": rec.get("canonical_url"),
        "match_eligibility": rec["match_eligibility"],  # carried through UNCHANGED
        "data_quality_status": rec["data_quality_status"],  # carried through UNCHANGED
        # component scores (audit trail)
        "salary_score": salary_score,
        "experience_score": exp_score,
        "skill_score": skill_score,
        "role_score": role_score,
        # component weights
        "salary_weight": WEIGHTS["salary"],
        "experience_weight": WEIGHTS["experience"],
        "skill_weight": WEIGHTS["skill"],
        "role_weight": WEIGHTS["role"],
        # component confidences (inputs to composite_confidence; audit trail)
        "salary_confidence": _c(salary, "salary_confidence", 1.0),
        "experience_confidence": _c(exp, "experience_confidence", 1.0),
        "skill_confidence": _c(skill, "skill_confidence", 1.0),
        "role_confidence": _c(role, "role_confidence", 1.0),
        # weighted contributions (audit trail)
        "salary_contribution": round(salary_contribution, 6),
        "experience_contribution": round(exp_contribution, 6),
        "skill_contribution": round(skill_contribution, 6),
        "role_contribution": round(role_contribution, 6),
        # implemented vs reserved weight
        "implemented_weight": IMPLEMENTED_WEIGHT,  # 0.80
        "reserved_weight": RESERVED_WEIGHT,  # 0.20
        # composite result
        "composite_score": composite_score,
        "composite_confidence": round(conf, 6),
        "recommendation_tier": recommendation_tier(composite_score),
        "composite_blocks": False,  # composite NEVER blocks
        "composite_rejection_reason": None,  # composite NEVER rejects
    }


def _index_by_job_id(path: Path) -> Dict[str, Dict[str, Any]]:
    entries: List[Dict[str, Any]] = json.load(open(path))
    return {e["job_id"]: e for e in entries}


def main() -> None:
    records: List[Dict[str, Any]] = json.load(open(IN_RECORDS))
    salary_by = _index_by_job_id(IN_SALARY)
    exp_by = _index_by_job_id(IN_EXPERIENCE)
    skill_by = _index_by_job_id(IN_SKILL)
    role_by = _index_by_job_id(IN_ROLE)

    rec_ids = {r["job_id"] for r in records}

    # --- hard join validation: every input set is 1:1 on job_id and equals records
    for label, m in (
        ("salary", salary_by),
        ("experience", exp_by),
        ("skill", skill_by),
        ("role", role_by),
    ):
        assert len(m) == len(
            records
        ), f"{label}: count mismatch ({len(m)} != {len(records)})"
        assert set(m.keys()) == rec_ids, f"{label}: job_id set mismatch"

    composites = [
        compute_composite(
            r,
            salary_by[r["job_id"]],
            exp_by[r["job_id"]],
            skill_by[r["job_id"]],
            role_by[r["job_id"]],
        )
        for r in records
    ]

    # --- invariant validation ------------------------------------------------
    assert len(composites) == len(records) == 20, "20 inputs must yield 20 composites"
    out_ids = [c["job_id"] for c in composites]
    assert len(set(out_ids)) == len(out_ids), "duplicate job_id in composite output"
    assert set(out_ids) == rec_ids, "composite job_id set must equal canonical set"

    assert all(
        c["salary_weight"] == 0.15
        and c["experience_weight"] == 0.20
        and c["skill_weight"] == 0.30
        and c["role_weight"] == 0.15
        for c in composites
    ), "weight mismatch"
    assert all(
        c["implemented_weight"] == 0.80 and c["reserved_weight"] == 0.20
        for c in composites
    ), "implemented/reserved weight mismatch"
    assert all(
        c["composite_blocks"] is False and c["composite_rejection_reason"] is None
        for c in composites
    ), "composite must never block/reject"

    # match_eligibility / data_quality_status unchanged from job_records.json
    rec_by = {r["job_id"]: r for r in records}
    assert all(
        c["match_eligibility"] == rec_by[c["job_id"]]["match_eligibility"]
        and c["data_quality_status"] == rec_by[c["job_id"]]["data_quality_status"]
        for c in composites
    ), "Phase2B fields must be carried through unchanged"

    # weighted contributions sum exactly to composite_score
    for c in composites:
        contrib_sum = (
            c["salary_contribution"]
            + c["experience_contribution"]
            + c["skill_contribution"]
            + c["role_contribution"]
        )
        assert (
            abs(contrib_sum - c["composite_score"]) < 1e-6
        ), f"contribution sum mismatch for {c['job_id']}"

    # no composite block / rejection
    assert sum(1 for c in composites if c["composite_blocks"]) == 0
    assert (
        sum(1 for c in composites if c["composite_rejection_reason"] is not None) == 0
    )

    with open(OUT, "w") as f:
        json.dump(composites, f, indent=2)

    tiers = Counter(c["recommendation_tier"] for c in composites)
    avg = sum(c["composite_score"] for c in composites) / len(composites)

    print("=== PHASE 2C - COMPOSITE SCORING (dry run) ===")
    print(f"Total composite records      : {len(composites)}")
    for k in ("RECOMMEND", "CONSIDER", "MONITOR"):
        print(f"  {k:9}: {tiers.get(k, 0)}")
    print(f"Average composite score      : {avg:.3f}")
    print(f"Implemented weight           : {IMPLEMENTED_WEIGHT}")
    print(f"Reserved weight (loc+workpl) : {RESERVED_WEIGHT}")
    print(
        f"Composite blocks/rejects     : {sum(1 for c in composites if c['composite_blocks'])}"
    )
    print(
        "Hard validation: 1:1 join, weights 0.15/0.20/0.30/0.15, implemented=0.80, "
        "reserved=0.20, blocks=false, rejections=null: PASS"
    )
    print(f"\nWritten: {OUT}")


def selftest() -> None:
    """Unit tests covering the locked composite behavior. Does not touch disk
    output; runs only in-memory cases."""
    ok = True

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if not cond:
            ok = False
        print(f"{'OK ' if cond else 'FAIL'}  {label}")

    # weight math
    check("weights sum to 0.80", IMPLEMENTED_WEIGHT == 0.80)
    check("reserved weight == 0.20", RESERVED_WEIGHT == 0.20)
    check(
        "implemented + reserved == 1.00",
        round(IMPLEMENTED_WEIGHT + RESERVED_WEIGHT, 6) == 1.00,
    )

    # confidence: all full confidence -> 1.0
    c = composite_confidence(
        {"salary": 1.0, "experience": 1.0, "skill": 1.0, "role": 1.0}
    )
    check("full confidence -> 1.0", abs(c - 1.0) < 1e-9)
    # confidence: one UNCLEAR (0.5) lowers it below 1.0
    c2 = composite_confidence(
        {"salary": 1.0, "experience": 1.0, "skill": 0.5, "role": 1.0}
    )
    check("UNCLEAR lowers confidence", c2 < 1.0)
    # confidence never negative
    c3 = composite_confidence(
        {"salary": 0.5, "experience": 0.5, "skill": 0.5, "role": 0.5}
    )
    check("confidence in [0,1]", 0.0 <= c3 <= 1.0)

    # tier bands (deterministic)
    check("score 0.575 -> RECOMMEND", recommendation_tier(0.575) == "RECOMMEND")
    check("score 0.25 -> RECOMMEND", recommendation_tier(0.25) == "RECOMMEND")
    check("score 0.19 -> CONSIDER", recommendation_tier(0.19) == "CONSIDER")
    check("score 0.10 -> CONSIDER", recommendation_tier(0.10) == "CONSIDER")
    check("score 0.075 -> MONITOR", recommendation_tier(0.075) == "MONITOR")
    check("score 0.0 -> MONITOR", recommendation_tier(0.0) == "MONITOR")
    check("score -0.8 -> MONITOR", recommendation_tier(-0.8) == "MONITOR")
    check("score 0.8 -> RECOMMEND", recommendation_tier(0.8) == "RECOMMEND")

    # composite score formula reproduces a known value:
    # salary 0.0 *0.15 + exp 0.5 *0.20 + skill 0.25 *0.30 + role 0.5 *0.15
    # = 0 + 0.10 + 0.075 + 0.075 = 0.25
    rec = {
        "job_id": "j1",
        "company_name": "Acme",
        "job_title": "X",
        "canonical_url": "http://x",
        "match_eligibility": "ELIGIBLE",
        "data_quality_status": "COMPLETE",
    }
    out = compute_composite(
        rec,
        {"job_id": "j1", "salary_score": 0.0, "salary_confidence": 1.0},
        {"job_id": "j1", "experience_score": 0.5, "experience_confidence": 1.0},
        {"job_id": "j1", "skill_score": 0.25, "skill_confidence": 0.75},
        {"job_id": "j1", "role_score": 0.5, "role_confidence": 1.0},
    )
    check("composite formula: 0.25", abs(out["composite_score"] - 0.25) < 1e-6)
    check(
        "contribution sum == composite",
        abs(
            out["salary_contribution"]
            + out["experience_contribution"]
            + out["skill_contribution"]
            + out["role_contribution"]
            - out["composite_score"]
        )
        < 1e-6,
    )
    check("salary_contribution 0.0", abs(out["salary_contribution"]) < 1e-9)
    check(
        "experience_contribution 0.10",
        abs(out["experience_contribution"] - 0.10) < 1e-9,
    )
    check("skill_contribution 0.075", abs(out["skill_contribution"] - 0.075) < 1e-9)
    check("role_contribution 0.075", abs(out["role_contribution"] - 0.075) < 1e-9)
    check("tier of 0.25 is RECOMMEND", out["recommendation_tier"] == "RECOMMEND")
    check("never blocks", out["composite_blocks"] is False)
    check("never rejects", out["composite_rejection_reason"] is None)
    check("eligibility carried through", out["match_eligibility"] == "ELIGIBLE")
    check("status carried through", out["data_quality_status"] == "COMPLETE")

    # missing salary (UNAVAILABLE, conf 1.0) stays neutral and does not lower confidence
    out2 = compute_composite(
        rec,
        {"job_id": "j1", "salary_score": 0.0, "salary_confidence": 1.0},
        {"job_id": "j1", "experience_score": 0.0, "experience_confidence": 1.0},
        {"job_id": "j1", "skill_score": 0.0, "skill_confidence": 0.5},  # UNCLEAR
        {"job_id": "j1", "role_score": 0.5, "role_confidence": 1.0},
    )
    check(
        "missing salary neutral (score unaffected)",
        abs(out2["salary_contribution"]) < 1e-9,
    )
    check(
        "UNCLEAR lowers confidence, not score",
        out2["composite_confidence"] < 1.0 and out2["composite_score"] >= 0.0,
    )
    check("score never negative from missing data", out2["composite_score"] >= 0.0)

    assert ok, "Composite self-test FAILED"
    print("\nComposite self-test: ALL PASS")


if __name__ == "__main__":
    selftest()
    main()

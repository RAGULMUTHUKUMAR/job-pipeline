#!/usr/bin/env python3
"""
Phase 2C - Skills Scoring (skills component only)

Consumes canonical Phase2B job_records.json (required_skills / preferred_skills)
and emits a skills score per record.

USER SKILL PROFILE (fixed)
    Tier 1 Core        : JavaScript, React, React Native, Node.js
    Tier 2 Supporting  : Tailwind CSS, MongoDB, SQL, REST API, Microservices,
                         Docker, AWS, AWS IAM, AWS S3
    Tier 3 Fundamental : Golang, DSA

SCORING
    Weighted matching: Tier1=1.0, Tier2=0.7, Tier3=0.4 per matched skill.
    Required matches contribute full weight; preferred matches contribute 0.5x.
    Total matched strength is mapped to one of the discrete levels.

CRITICAL RULE: skills NEVER cause rejection or blocking.
    skill_blocks=false and skill_rejection_reason=null on every record,
    regardless of match quality. Missing job skills are NOT a poor match
    (treated as UNCLEAR / neutral), never a rejection.
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
IN_RECORDS = BASE_DIR / "output" / "job_records.json"
OUT = BASE_DIR / "output" / "phase2c_skill_scores.json"

# --- user profile -----------------------------------------------------------
TIER1 = {"javascript", "react", "react native", "node.js"}
TIER2 = {
    "tailwind css",
    "mongodb",
    "sql",
    "rest api",
    "microservices",
    "docker",
    "aws",
    "aws iam",
    "aws s3",
}
TIER3 = {"golang", "dsa"}

TIER_WEIGHT = {"core": 1.0, "supporting": 0.7, "fundamental": 0.4}

# --- conservative normalization (alias -> canonical user skill) ------------
# Longest phrases first so "react native" wins over "react", "restful api"
# over "rest", "go programming language" over "go", etc.
_ALIASES = [
    ("data structures and algorithms", "dsa"),
    ("go programming language", "golang"),
    ("go programming", "golang"),
    ("go language", "golang"),
    ("go lang", "golang"),
    ("amazon web services", "aws"),
    ("amazon s3", "aws s3"),
    ("react native", "react native"),
    ("tailwind css", "tailwind css"),
    ("tailwindcss", "tailwind css"),
    ("microservices", "microservices"),
    ("micro services", "microservices"),
    ("micro-service", "microservices"),
    ("microservice", "microservices"),
    ("restful apis", "rest api"),
    ("restful api", "rest api"),
    ("rest apis", "rest api"),
    ("rest api", "rest api"),
    ("docker container", "docker"),
    ("nodejs", "node.js"),
    ("node js", "node.js"),
    ("node.js", "node.js"),
    ("reactjs", "react"),
    ("react js", "react"),
    ("react.js", "react"),
    ("mongo db", "mongodb"),
    ("aws iam", "aws iam"),
    ("javascript", "javascript"),
    ("mongodb", "mongodb"),
    ("golang", "golang"),
    ("react", "react"),
    ("node", "node.js"),
    ("docker", "docker"),
    ("aws", "aws"),
    ("rest", "rest api"),
    ("tailwind", "tailwind css"),
    ("sql", "sql"),
    ("mongo", "mongodb"),
    ("dsa", "dsa"),
    ("s3", "aws s3"),
    ("js", "javascript"),
    ("go", "golang"),  # kept last/weakest; only matches as a whole word
]
_ALIASES.sort(key=lambda a: len(a[0]), reverse=True)

PLACEHOLDERS = {"", "na", "n/a", "none", "nil", "-", "n.a.", "null", "not applicable"}

# Nominal weight this dimension would carry in a future composite Phase2C score
# (documentation only - composite scoring is NOT implemented here).
SKILL_WEIGHT = 0.30


def _clean(s: str) -> str:
    t = (s or "").lower().strip()
    t = re.sub(r"[^a-z0-9 ]", " ", t)  # punctuation -> space (react.js -> react js)
    return re.sub(r"\s+", " ", t).strip()


def _is_real(s: Any) -> bool:
    return (s or "").strip().lower() not in PLACEHOLDERS


def normalize_to_user_skill(skill: str) -> Optional[str]:
    """Map a job-skill phrase to a canonical user skill, or None if no match.

    Word-boundary matching prevents over-matching (e.g. 'go' not matched inside
    'google'; 'java' never becomes 'javascript'; 'kubernetes' != docker).
    """
    cleaned = _clean(skill)
    if not cleaned:
        return None
    for alias, canon in _ALIASES:
        if re.search(r"\b" + re.escape(alias) + r"\b", cleaned):
            return canon
    return None


def _tier(canon: str) -> str:
    if canon in TIER1:
        return "core"
    if canon in TIER2:
        return "supporting"
    return "fundamental"


def _classify(strength: float) -> Tuple[str, float]:
    if strength >= 2.5:
        return "EXCELLENT", 1.0
    if strength >= 1.5:
        return "GOOD", 0.75
    if strength >= 0.7:
        return "PARTIAL", 0.5
    if strength >= 0.25:
        return "WEAK", 0.25
    return "NONE", 0.0


def score_skill_lists(required: List[str], preferred: List[str]) -> Dict[str, Any]:
    """Score from explicit required/preferred skill lists (used by unit tests)."""
    real_req = [s for s in (required or []) if _is_real(s)]
    real_pref = [s for s in (preferred or []) if _is_real(s)]

    matched: Dict[str, str] = {}  # canon -> tier
    strength = 0.0

    # required: full tier weight
    for s in real_req:
        canon = normalize_to_user_skill(s)
        if canon:
            t = _tier(canon)
            strength += TIER_WEIGHT[t]
            matched[canon] = t
    # preferred: half weight, positive but weaker; never a "problem" if absent
    for s in real_pref:
        canon = normalize_to_user_skill(s)
        if canon:
            t = _tier(canon)
            strength += 0.5 * TIER_WEIGHT[t]
            matched.setdefault(canon, t)

    has_evidence = bool(real_req or real_pref)

    if not has_evidence:
        return {
            "skill_score": 0.0,
            "skill_confidence": 0.5,  # missing/ambiguous evidence
            "skill_fit": "UNCLEAR",
            "matched_core_skills": [],
            "matched_supporting_skills": [],
            "matched_fundamental_skills": [],
            "missing_important_skills": [],
            "normalized_job_skills": [],
            "skill_blocks": False,
            "skill_rejection_reason": None,
        }

    label, score = _classify(strength)
    if label in ("EXCELLENT", "GOOD"):
        conf = 1.0
    elif label in ("PARTIAL", "WEAK"):
        conf = 0.75
    else:  # NONE - evidence present but no useful overlap
        conf = 1.0

    matched_core = sorted(c for c, t in matched.items() if t == "core")
    matched_supporting = sorted(c for c, t in matched.items() if t == "supporting")
    matched_fundamental = sorted(c for c, t in matched.items() if t == "fundamental")

    matched_required = {normalize_to_user_skill(s) for s in real_req}
    matched_required.discard(None)
    missing_important = sorted(
        {s for s in real_req if normalize_to_user_skill(s) not in matched_required}
    )

    return {
        "skill_score": score,
        "skill_confidence": conf,
        "skill_fit": label,
        "matched_core_skills": matched_core,
        "matched_supporting_skills": matched_supporting,
        "matched_fundamental_skills": matched_fundamental,
        "missing_important_skills": missing_important,
        "normalized_job_skills": [_clean(s) for s in real_req + real_pref],
        "skill_blocks": False,
        "skill_rejection_reason": None,
    }


def score_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Score a single canonical record."""
    result = score_skill_lists(
        rec.get("required_skills") or [], rec.get("preferred_skills") or []
    )
    result = dict(result)
    result.update(
        {
            "job_id": rec["job_id"],
            "source_job_id": rec["source_job_id"],
            "job_title": rec["job_title"],
            "company_name": rec["company_name"],
            "skill_weight": SKILL_WEIGHT,
        }
    )
    return result


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------
def selftest() -> None:
    cases = [
        (["React", "JavaScript", "Node.js"], [], "EXCELLENT", 1.0, "React+JS+Node"),
        (
            ["React", "Node.js", "MongoDB"],
            [],
            {"GOOD", "EXCELLENT"},
            None,
            "React+Node+MongoDB",
        ),
        (["React"], [], {"PARTIAL", "WEAK"}, None, "React only"),
        (["Docker", "AWS"], [], {"PARTIAL", "WEAK"}, None, "Docker+AWS"),
        (["Golang"], [], "WEAK", 0.25, "Golang only"),
        (["Java", "Spring Boot"], [], "NONE", 0.0, "Java+SpringBoot"),
        (["React.js", "NodeJS", "Mongo DB"], [], None, None, "normalization+match"),
        (["React Native"], [], None, None, "React Native != React"),
        (["Java"], [], "NONE", 0.0, "Java must NOT match JavaScript"),
        (["Kubernetes"], [], "NONE", 0.0, "Kubernetes must NOT match Docker"),
        ([], [], "UNCLEAR", 0.0, "missing skills"),
        (
            ["Java", "Spring Boot", "Kafka", "Kubernetes"],
            [],
            "NONE",
            0.0,
            "unrelated stack",
        ),
    ]
    ok = True

    def run(required, preferred, want_fit, want_score):
        r = score_skill_lists(required, preferred)
        if want_fit is None:
            fit_ok = True  # fit checked via targeted asserts below
        elif isinstance(want_fit, str):
            fit_ok = r["skill_fit"] == want_fit
        else:
            fit_ok = r["skill_fit"] in want_fit
        score_ok = r["skill_score"] == want_score if want_score is not None else True
        return r, fit_ok and score_ok

    for required, preferred, want_fit, want_score, label in cases:
        r, passed = run(required, preferred, want_fit, want_score)
        mark = "OK " if passed else "FAIL"
        if not passed:
            ok = False
        print(f"{mark}  {label:34} -> {r['skill_fit']:10} score={r['skill_score']}")

    # targeted normalization / no-over-match checks
    assert normalize_to_user_skill("React Native") == "react native", "RN != React"
    assert normalize_to_user_skill("React.js") == "react"
    assert normalize_to_user_skill("NodeJS") == "node.js"
    assert normalize_to_user_skill("Mongo DB") == "mongodb"
    assert normalize_to_user_skill("JavaScript") == "javascript"
    assert normalize_to_user_skill("Java") is None, "Java must not be javascript"
    assert normalize_to_user_skill("Kubernetes") is None, "Kubernetes != docker"
    assert normalize_to_user_skill("AWS") == "aws"
    assert normalize_to_user_skill("Azure") is None, "Azure != AWS"
    print("  normalization & no-over-match checks: OK")

    # missing skills -> UNCLEAR / 0.0 / 0.5
    m = score_skill_lists([], [])
    assert (
        m["skill_fit"] == "UNCLEAR"
        and m["skill_score"] == 0.0
        and m["skill_confidence"] == 0.5
    )
    print("  missing-skills UNCLEAR/0.0/conf0.5: OK")

    assert ok, "Skills self-test FAILED"
    print("\nSkills self-test: ALL PASS")


def main() -> None:
    selftest()
    records: List[Dict[str, Any]] = json.load(open(IN_RECORDS))
    scores = [score_record(r) for r in records]

    with open(OUT, "w") as f:
        json.dump(scores, f, indent=2)

    fits = Counter(s["skill_fit"] for s in scores)
    avg = sum(s["skill_score"] for s in scores) / len(scores)
    blocks = [s for s in scores if s["skill_blocks"]]
    rejects = [s for s in scores if s["skill_rejection_reason"] is not None]

    print("\n=== PHASE 2C - SKILLS SCORING (dry run) ===")
    print(f"Total records          : {len(scores)}")
    for k in ("EXCELLENT", "GOOD", "PARTIAL", "WEAK", "NONE", "UNCLEAR"):
        print(f"  {k:10}: {fits.get(k, 0)}")
    print(f"Average skill score    : {avg:.3f}")
    print(f"Skill blocks           : {len(blocks)}")
    print(f"Skill rejections       : {len(rejects)}")

    # hard validation
    assert all(
        s["skill_blocks"] is False for s in scores
    ), "A record has skill_blocks != false!"
    assert all(
        s["skill_rejection_reason"] is None for s in scores
    ), "A record has a skill rejection!"
    assert not blocks and not rejects
    print(
        "Hard validation: skill_blocks==false and skill_rejection_reason==null for ALL records: PASS"
    )
    print(f"\nWritten: {OUT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Phase 2C - Job Role / Title Relevance Scoring (role component only)

Consumes canonical Phase2B job_records.json (job_title) and emits a role score.

USER TARGET ROLE PROFILE
    PRIMARY   : Frontend/React/React Native/JavaScript/Node.js/Full Stack/MERN/
                Software Engineer - Frontend|Full Stack  -> STRONG  +1.0
    SECONDARY : Software/Web/Application/Backend/Mobile/Node.js Backend
                                                          -> GOOD    +0.6
    GENERAL   : Generic Software Engineer/Developer, no conflicting spec
                                                          -> GENERAL +0.5
    LOW       : Java/Python/.NET/C#/C++/DevOps/DevSecOps/Data/ML/QA/Test/
                SAP/Salesforce/Mainframe                   -> LOW     -0.5
    UNCLEAR   : missing/ambiguous title                    -> UNCLEAR  0.0

RULES
    - Conservative whole-word matching (java != javascript, React != React Native,
      Kubernetes-style over-matching avoided).
    - Seniority words (Senior/Staff/Lead/Principal) never affect the fit.
    - A specialization mismatch (LOW) takes precedence over generic words like
      Engineer/Developer.
    - Role score NEVER causes rejection or blocking.

CRITICAL: role_blocks=false and role_rejection_reason=null on every record.
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
IN_RECORDS = BASE_DIR / "output" / "job_records.json"
OUT = BASE_DIR / "output" / "phase2c_role_scores.json"

ROLE_SCORE = {"STRONG": 1.0, "GOOD": 0.6, "GENERAL": 0.5, "LOW": -0.5, "UNCLEAR": 0.0}

# Nominal weight this dimension would carry in a future composite Phase2C score
# (documentation only - composite scoring is NOT implemented here).
ROLE_WEIGHT = 0.15

# Level / seniority tokens that must not affect role fit (handled elsewhere).
_SENIORITY = [
    "senior",
    "staff",
    "lead",
    "principal",
    "junior",
    "jr",
    "mid",
    "level",
    "entry",
]
_LEVELS = r"\b(?:iii|ii|iv|vi|v|xiii|xii|xi|ix|i)\b"


def normalize_title(title: Optional[str]) -> str:
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9 ]", " ", t)  # punctuation -> space
    t = re.sub(r"\b\d+\b", " ", t)  # level digits ("Engineer 2")
    t = re.sub(_LEVELS, " ", t)  # level roman numerals ("Developer III")
    for w in _SENIORITY:  # seniority must not affect fit
        t = re.sub(r"\b" + w + r"\b", " ", t)
    for a, b in {
        "front end": "frontend",
        "back end": "backend",
        "react js": "react",
        "reactjs": "react",
        "node js": "nodejs",
        "full stack": "fullstack",
        "mern stack": "mernstack",
        "dot net": "dotnet",
        "c sharp": "csharp",
        "c plus plus": "cpp",
    }.items():
        t = re.sub(r"\b" + re.escape(a) + r"\b", b, t)
    return re.sub(r"\s+", " ", t).strip()


_LOW_PATTERNS = [  # (category label, regex) - whole word
    ("DevSecOps", r"\bdevsecops\b"),
    ("DevOps", r"\bdevops\b"),
    ("Java", r"\bjava\b"),  # \bjava\b never matches inside "javascript"
    ("Python", r"\bpython\b"),
    (".NET", r"\bdotnet\b"),
    ("C#", r"\bcsharp\b"),
    ("C++", r"\bcpp\b"),
    ("Data", r"\bdata\b"),
    ("Machine Learning", r"\bmachine learning\b"),
    ("QA", r"\bqa\b"),
    ("Test", r"\btest\b"),
    ("SAP", r"\bsap\b"),
    ("Salesforce", r"\bsalesforce\b"),
    ("Mainframe", r"\bmainframe\b"),
]


def _detect_low(t: str) -> Optional[str]:
    for label, pat in _LOW_PATTERNS:
        if re.search(pat, t):
            return label
    return None


def _detect_primary(t: str) -> Optional[str]:
    if re.search(r"\bfrontend\b", t):
        return "Frontend"
    if re.search(r"\breact native\b", t):
        return "React Native"  # before bare "react"
    if re.search(r"\breact\b", t):
        return "React"
    if re.search(r"\bjavascript\b", t):
        return "JavaScript"
    if re.search(r"\bfullstack\b|\bmernstack\b|\bmern\b", t):
        return "Full Stack"
    # Node.js is primary unless explicitly a backend role
    if re.search(r"\bnodejs\b|\bnode\b", t) and not re.search(r"\bbackend\b", t):
        return "Node.js"
    return None


def _detect_secondary(t: str) -> Optional[str]:
    if re.search(r"\bbackend\b", t):
        return "Backend"  # catches "Node.js Backend Developer"
    if re.search(r"\bmobile\b", t):
        return "Mobile"
    if re.search(r"\bweb\b", t):
        return "Web"
    if re.search(r"\bapplication\b", t):
        return "Application"
    return None


def classify_role(title: Optional[str]) -> Tuple[str, float, float, str, str]:
    """Return (role_fit, role_score, role_confidence, role_category, reason)."""
    t = normalize_title(title)
    if not t:
        return "UNCLEAR", 0.0, 0.5, "Unclear", "Title missing or empty"

    # LOW takes precedence over generic Engineer/Developer words
    low = _detect_low(t)
    if low:
        return "LOW", -0.5, 1.0, "Low", f"Lower-relevance specialization: {low}"

    prim = _detect_primary(t)
    if prim:
        return "STRONG", 1.0, 1.0, prim, f"Primary target role: {prim}"

    sec = _detect_secondary(t)
    if sec:
        return "GOOD", 0.6, 1.0, sec, f"Secondary/relevant role: {sec}"

    if re.search(r"\bsoftware\b", t) or re.search(r"\bengineer\b|\bdeveloper\b", t):
        return (
            "GENERAL",
            0.5,
            1.0,
            "General Software",
            "Generic software role (no conflicting specialization)",
        )

    return "UNCLEAR", 0.0, 0.5, "Unclear", "Role title ambiguous/unrecognized"


def score_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    fit, score, conf, category, reason = classify_role(rec.get("job_title"))
    return {
        "job_id": rec["job_id"],
        "source_job_id": rec["source_job_id"],
        "job_title": rec["job_title"],
        "company_name": rec["company_name"],
        "role_score": score,
        "role_confidence": conf,
        "role_fit": fit,
        "role_category": category,
        "role_reason": reason,
        "role_weight": ROLE_WEIGHT,
        "role_blocks": False,  # role NEVER blocks
        "role_rejection_reason": None,  # role NEVER rejects
    }


def selftest() -> None:
    cases = [
        ("React Developer", "STRONG", 1.0),
        ("Senior React Engineer", "STRONG", 1.0),
        ("React Native Developer", "STRONG", 1.0),
        ("Frontend Engineer", "STRONG", 1.0),
        ("Full Stack Developer", "STRONG", 1.0),
        ("MERN Stack Developer", "STRONG", 1.0),
        ("Node.js Developer", "STRONG", 1.0),
        ("Software Engineer", "GENERAL", 0.5),
        ("Software Developer", "GENERAL", 0.5),
        ("Backend Engineer", "GOOD", 0.6),
        ("Java Developer", "LOW", -0.5),
        ("Python Developer", "LOW", -0.5),
        ("DevOps Engineer", "LOW", -0.5),
        ("Data Engineer", "LOW", -0.5),
        ("QA Engineer", "LOW", -0.5),
        ("", "UNCLEAR", 0.0),
    ]
    ok = True
    for title, want_fit, want_score in cases:
        fit, score, conf, cat, reason = classify_role(title)
        passed = fit == want_fit and score == want_score
        if not passed:
            ok = False
        print(
            f"{'OK ' if passed else 'FAIL'}  {title or '<missing>':28} -> {fit:9} {score:+.1f}"
        )

    # no-over-match / specificity checks
    assert (
        classify_role("React Native Developer")[3] == "React Native"
    ), "RN must be its own category"
    assert classify_role("Java Developer")[3] == "Low", "Java must not be JavaScript"
    assert (
        classify_role("Data Engineer")[0] == "LOW"
    ), "Data Engineer must not be GENERAL"
    assert classify_role("DevOps Engineer")[0] == "LOW", "DevOps must not be GENERAL"
    assert (
        classify_role("Senior React Engineer")[0] == "STRONG"
    ), "seniority must not lower fit"
    assert (
        classify_role("Node.js Backend Developer")[0] == "GOOD"
    ), "Node backend is secondary"
    print("  no-over-match & specificity checks: OK")
    assert ok, "Role self-test FAILED"
    print("\nRole self-test: ALL PASS")


def main() -> None:
    selftest()
    records: List[Dict[str, Any]] = json.load(open(IN_RECORDS))
    scores = [score_record(r) for r in records]

    with open(OUT, "w") as f:
        json.dump(scores, f, indent=2)

    fits = Counter(s["role_fit"] for s in scores)
    avg = sum(s["role_score"] for s in scores) / len(scores)
    blocks = [s for s in scores if s["role_blocks"]]
    rejects = [s for s in scores if s["role_rejection_reason"] is not None]

    print("\n=== PHASE 2C - ROLE SCORING (dry run) ===")
    print(f"Total records          : {len(scores)}")
    for k in ("STRONG", "GOOD", "GENERAL", "LOW", "UNCLEAR"):
        print(f"  {k:9}: {fits.get(k, 0)}")
    print(f"Average role score     : {avg:.3f}")
    print(f"Role blocks            : {len(blocks)}")
    print(f"Role rejections        : {len(rejects)}")

    assert all(
        s["role_blocks"] is False for s in scores
    ), "A record has role_blocks != false!"
    assert all(
        s["role_rejection_reason"] is None for s in scores
    ), "A record has a role rejection!"
    assert not blocks and not rejects
    print(
        "Hard validation: role_blocks==false and role_rejection_reason==null for ALL records: PASS"
    )
    print(f"\nWritten: {OUT}")


if __name__ == "__main__":
    main()

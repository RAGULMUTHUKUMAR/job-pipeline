#!/usr/bin/env python3
"""
Phase 2C - Location Scoring (location/geography component only)

Consumes canonical Phase2B job_records.json and emits a location score per record.

APPROVED LOCATION POLICY (scoring component only):
    The dataset is 100% India (country=IN). User is a JavaScript/React/Node.js
    software engineer. Location scoring evaluates geographic preference for
    onsite/hybrid roles. Remote roles are scored separately in Workplace scoring.

    Score mapping:
        PREFERRED   -> +1.0   (major tech hubs with strong JS/React/Node market)
        ACCEPTABLE  -> +0.5   (other Indian cities with tech presence)
        UNAVAILABLE ->  0.0   (neutral; missing location data)
        UNCLEAR     ->  0.0   (neutral, lower confidence; ambiguous/unparsable)

    Location NEVER causes hard rejection or blocking.
    location_blocks=false and location_rejection_reason=null on every record.

    Remote/Hybrid/Onsite workplace mode is scored in Workplace scoring,
    NOT here. This scorer only evaluates the geographic location (city/state).
"""

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
IN_RECORDS = BASE_DIR / "output" / "job_records.json"
OUT = BASE_DIR / "output" / "phase2c_location_scores.json"

# Score on [-1.0, 1.0]; 0.0 = neutral.
LOCATION_SCORE = {
    "PREFERRED": 1.0,
    "ACCEPTABLE": 0.5,
    "UNAVAILABLE": 0.0,  # neutral
    "UNCLEAR": 0.0,  # neutral, lower confidence
}

# Confidence in the location signal on [0,1].
LOCATION_CONFIDENCE = {
    "PREFERRED": 1.0,
    "ACCEPTABLE": 1.0,
    "UNAVAILABLE": 1.0,  # neutral; no penalty
    "UNCLEAR": 0.5,  # lower confidence
}

# Nominal weight this dimension would carry in a future composite Phase2C score
LOCATION_WEIGHT = 0.10

# --- Approved geographic preferences (India) ---
# PREFERRED: Major tech hubs with strong JavaScript/React/Node.js market
PREFERRED_CITIES = {
    "BENGALURU",  # Bangalore - India's Silicon Valley
    "HYDERABAD",  # Hyderabad - major tech hub
    "CHENNAI",  # Chennai - growing tech scene
    "MUMBAI",  # Mumbai - financial/tech center
    "PUNE",  # Pune - major IT hub
    "GURGAON",  # Gurgaon/Gurugram - NCR tech hub
    "NOIDA",  # Noida - NCR tech hub
    "DELHI",  # Delhi - NCR
}

# ACCEPTABLE: Other Indian cities with tech presence
ACCEPTABLE_CITIES = {
    "COIMBATORE",  # Coimbatore - emerging
    "THIRUVANANTHAPURAM",  # Trivandrum - Technopark
    "KOCHI",  # Kochi - Infopark
    "KOLKATA",  # Kolkata - Sector V
    "AHMEDABAD",  # Ahmedabad - GIFT City
    "VADODARA",  # Vadodara
    "JAIPUR",  # Jaipur
    "INDORE",  # Indore
    "NAGPUR",  # Nagpur
    "LUCKNOW",  # Lucknow
    "BHUBANESWAR",  # Bhubaneswar
    "VISAKHAPATNAM",  # Visakhapatnam
    "MYSORE",  # Mysore
}

# Known Indian states for fallback matching
INDIAN_STATES = {
    "KARNATAKA",
    "TELANGANA",
    "TAMIL NADU",
    "MAHARASHTRA",
    "DELHI",
    "HARYANA",
    "UTTAR PRADESH",
    "GUJARAT",
    "KERALA",
    "WEST BENGAL",
    "ODISHA",
    "ANDHRA PRADESH",
    "MADHYA PRADESH",
    "RAJASTHAN",
    "PUNJAB",
    "HIMACHAL PRADESH",
}


def normalize_city(city: Optional[str]) -> str:
    """Normalize city name to uppercase for matching."""
    if not city:
        return ""
    c = city.upper().strip()
    # Handle common variations
    replacements = {
        "BANGALORE": "BENGALURU",
        "BANGLORE": "BENGALURU",
        "TRIVANDRUM": "THIRUVANANTHAPURAM",
        "CALCUTTA": "KOLKATA",
        "MADRAS": "CHENNAI",
        "BOMBAY": "MUMBAI",
        "POONA": "PUNE",
        "GURGAON": "GURGAON",
        "GURUGRAM": "GURGAON",
    }
    return replacements.get(c, c)


def normalize_state(state: Optional[str]) -> str:
    """Normalize state name to uppercase for matching."""
    if not state:
        return ""
    s = state.upper().strip()
    replacements = {
        "TAMILNADU": "TAMIL NADU",
    }
    return replacements.get(s, s)


def classify_location(
    city: Optional[str], state: Optional[str], country: Optional[str]
) -> str:
    """
    Classify location into PREFERRED / ACCEPTABLE / UNAVAILABLE / UNCLEAR.

    Priority:
    1. Match normalized_city against PREFERRED/ACCEPTABLE city lists
    2. Fall back to normalized_state if city unavailable
    3. If country != IN, treat as UNAVAILABLE (no policy for non-India)
    4. Missing/unparsable -> UNAVAILABLE/UNCLEAR
    """
    # Missing location data
    if not city and not state and not country:
        return "UNAVAILABLE"

    # Non-India: no approved policy, treat as UNAVAILABLE neutral
    if country and country != "IN":
        return "UNAVAILABLE"

    norm_city = normalize_city(city)
    norm_state = normalize_state(state)

    # Try city match first (most specific)
    if norm_city:
        if norm_city in PREFERRED_CITIES:
            return "PREFERRED"
        if norm_city in ACCEPTABLE_CITIES:
            return "ACCEPTABLE"
        # City known but not in our lists - could be unclear if it looks like a real city
        # but for now treat as UNAVAILABLE (no policy opinion)

    # Fall back to state match
    if norm_state:
        if norm_state in (
            "KARNATAKA",
            "TELANGANA",
            "TAMIL NADU",
            "MAHARASHTRA",
            "DELHI",
            "HARYANA",
        ):
            return "PREFERRED"
        if norm_state in INDIAN_STATES:
            return "ACCEPTABLE"

    # We have location data but couldn't classify - unclear
    if city or state:
        return "UNCLEAR"

    return "UNAVAILABLE"


def score_location(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Location scoring for a single canonical record. Never blocks/rejects."""
    city = rec.get("normalized_city")
    state = rec.get("normalized_state")
    country = rec.get("country")

    interp = classify_location(city, state, country)
    score = LOCATION_SCORE[interp]
    conf = LOCATION_CONFIDENCE[interp]

    # Build explanation note
    if interp == "PREFERRED":
        note = f"Location in preferred tech hub ({city}, {state}). Positive location contribution."
    elif interp == "ACCEPTABLE":
        note = f"Location in acceptable city ({city}, {state}). Normal location contribution."
    elif interp == "UNCLEAR":
        note = f"Location present ({city}, {state}) but not in approved lists. Neutral score with reduced confidence."
    else:  # UNAVAILABLE
        if not city and not state:
            note = "Location unavailable. Neutral (0) score, no penalty."
        else:
            note = f"Location ({city}, {state}, {country}) outside approved policy scope. Neutral (0) score, no penalty."

    return {
        "job_id": rec["job_id"],
        "source_job_id": rec["source_job_id"],
        "job_title": rec["job_title"],
        "company_name": rec["company_name"],
        "location_raw": rec.get("location"),
        "normalized_city": city,
        "normalized_state": state,
        "country": country,
        "location_interpretation": interp,
        "location_score": score,
        "location_confidence": conf,
        "location_weight": LOCATION_WEIGHT,
        "location_deprioritized": False,  # no negative scores in this policy
        "location_blocks": False,  # location NEVER blocks
        "location_rejection_reason": None,  # location NEVER rejects
        "score_notes": note,
    }


def selftest() -> None:
    """Unit tests covering the approved location behavior."""
    cases = [
        # (city, state, country, want_interp, description)
        ("BENGALURU", "KARNATAKA", "IN", "PREFERRED", "Bangalore preferred"),
        ("Hyderabad", "TELANGANA", "IN", "PREFERRED", "Hyderabad preferred"),
        ("Chennai", "TAMIL NADU", "IN", "PREFERRED", "Chennai preferred"),
        ("Mumbai", "MAHARASHTRA", "IN", "PREFERRED", "Mumbai preferred"),
        ("Pune", "MAHARASHTRA", "IN", "PREFERRED", "Pune preferred"),
        ("Gurgaon", "HARYANA", "IN", "PREFERRED", "Gurgaon preferred"),
        ("Noida", "UTTAR PRADESH", "IN", "PREFERRED", "Noida preferred"),
        ("Delhi", "DELHI", "IN", "PREFERRED", "Delhi preferred"),
        ("Coimbatore", "TAMIL NADU", "IN", "ACCEPTABLE", "Coimbatore acceptable"),
        ("Thiruvananthapuram", "KERALA", "IN", "ACCEPTABLE", "Trivandrum acceptable"),
        ("Kochi", "KERALA", "IN", "ACCEPTABLE", "Kochi acceptable"),
        ("Kolkata", "WEST BENGAL", "IN", "ACCEPTABLE", "Kolkata acceptable"),
        ("Ahmedabad", "GUJARAT", "IN", "ACCEPTABLE", "Ahmedabad acceptable"),
        ("Bangalore", "KARNATAKA", "IN", "PREFERRED", "Bangalore alias"),
        ("Trivandrum", "KERALA", "IN", "ACCEPTABLE", "Trivandrum alias"),
        (
            "UnknownCity",
            "KARNATAKA",
            "IN",
            "PREFERRED",
            "Unknown city, preferred state",
        ),
        ("UnknownCity", "KERALA", "IN", "ACCEPTABLE", "Unknown city, acceptable state"),
        (
            "RandomCity",
            "RANDOMSTATE",
            "IN",
            "UNCLEAR",
            "Unrecognized city/state in India",
        ),
        (None, None, "IN", "UNAVAILABLE", "No city/state, country=IN"),
        (None, None, "US", "UNAVAILABLE", "Non-India country"),
        (None, None, None, "UNAVAILABLE", "Completely missing location"),
        ("", "", "IN", "UNAVAILABLE", "Empty strings"),
    ]

    ok = True
    for city, state, country, want, label in cases:
        rec = {"normalized_city": city, "normalized_state": state, "country": country}
        got = classify_location(city, state, country)
        passed = got == want
        if not passed:
            ok = False
        mark = "OK " if passed else "FAIL"
        print(f"{mark}  {label:40} -> {got:12} (want {want})")

    # Test score/confidence mappings
    assert LOCATION_SCORE["PREFERRED"] == 1.0
    assert LOCATION_SCORE["ACCEPTABLE"] == 0.5
    assert LOCATION_SCORE["UNAVAILABLE"] == 0.0
    assert LOCATION_SCORE["UNCLEAR"] == 0.0
    assert LOCATION_CONFIDENCE["PREFERRED"] == 1.0
    assert LOCATION_CONFIDENCE["ACCEPTABLE"] == 1.0
    assert LOCATION_CONFIDENCE["UNAVAILABLE"] == 1.0
    assert LOCATION_CONFIDENCE["UNCLEAR"] == 0.5
    assert LOCATION_WEIGHT == 0.10
    print("  score/confidence/weight constants: OK")

    assert ok, "Location self-test FAILED"
    print("\nLocation self-test: ALL PASS")


def main() -> None:
    selftest()
    records: List[Dict[str, Any]] = json.load(open(IN_RECORDS))
    scores = [score_location(r) for r in records]

    with open(OUT, "w") as f:
        json.dump(scores, f, indent=2)

    by_interp = Counter(s["location_interpretation"] for s in scores)
    print("\n=== PHASE 2C - LOCATION SCORING (dry run) ===")
    print(f"Total records scored         : {len(scores)}")
    for k in ("PREFERRED", "ACCEPTABLE", "UNAVAILABLE", "UNCLEAR"):
        print(f"  {k:12}: {by_interp.get(k, 0)}")
    print(
        f"Location blocks/rejects      : {sum(1 for s in scores if s['location_blocks'])}"
    )
    print(
        f"Location deprioritized       : {sum(1 for s in scores if s['location_deprioritized'])}"
    )
    rejected = [s for s in scores if s["location_rejection_reason"] is not None]
    print(f"Records rejected due to location: {len(rejected)}")
    assert not rejected, "Location must never cause rejection!"
    print(f"\nWritten: {OUT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Phase 2B - Job Normalization & Deduplication Pipeline
=====================================================
Transforms raw Apify LinkedIn job records into canonical Job Records.

Frozen architecture: Apify Discovery -> Normalize -> Deduplicate -> Match ->
Score -> Tailor Resume -> Cover Letter -> Google Drive -> Human Review ->
User Applies -> Track -> Feedback

Design (approved, revised) implements:
  - Evidence-based workplace classification (negatives take precedence,
    conflicts -> UNKNOWN + WORKPLACE_CONFLICT, never guess)
  - Two-tier cross-company description handling
  - Experience extraction separate from seniority (with seniority_source)
  - Explicit salary interpretation policy
  - match_eligibility contract (ELIGIBLE / REVIEW / BLOCKED)
  - Deterministic dedup: source_job_id -> canonical_url -> normalized URL
    -> content fingerprint; survivors preserved, duplicates retained
  - Permanent preservation of all raw records

No external dependencies beyond stdlib.
"""

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
INPUT_RAW = BASE_DIR / "input" / "raw_records.json"
OUT_DIR = BASE_DIR / "output"
DATASET_ID = "HrBBKonRmbVHjiiio"
DISCOVERED_DATE = "2026-08-10"
SOURCE = "linkedin"

NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# ---------------------------------------------------------------------------
# Gazetteers / static maps
# ---------------------------------------------------------------------------
COUNTRY_ISO = {"india": "IN", "united states": "US", "usa": "US"}
CITY_GAZETTEER = {
    "bengaluru": "BENGALURU",
    "bangalore": "BENGALURU",
    "chennai": "CHENNAI",
    "madras": "CHENNAI",
    "hyderabad": "HYDERABAD",
    "coimbatore": "COIMBATORE",
    "trivandrum": "THIRUVANANTHAPURAM",
}

SENIORITY_LINKEDIN = {
    "internship": "JUNIOR",
    "entry level": "JUNIOR",
    "associate": "MID",  # NOT assumed JUNIOR; mapped as its own level
    "mid-senior level": "MID",
    "director": "LEAD",
    "executive": "LEAD",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _norm_desc(html_text: Optional[str]) -> str:
    """Normalize description text for fingerprinting & skill extraction."""
    if not html_text:
        return ""
    import html as _html

    text = _html.unescape(html_text)
    text = re.sub(r"<[^>]+>", " ", text)  # strip tags (defensive)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


# ---------------------------------------------------------------------------
# 1. URL normalization
# ---------------------------------------------------------------------------
_TRACKING_PARAMS = {"position", "pagenum", "refid", "trackingid", "fp_ref", "trk"}


def extract_job_id(link: str) -> Optional[int]:
    # Job id is the trailing integer after the LAST hyphen in the /jobs/view slug.
    m = re.search(r"/jobs/view/(?:.+)-(\d+)", link or "")
    return int(m.group(1)) if m else None


def normalize_url(link: str) -> Optional[str]:
    """Strip tracking params; canonicalize host+path for a job view URL."""
    if not link:
        return None
    try:
        from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

        u = urlparse(link)
        path = u.path.rstrip("/")
        m = re.search(r"^(/jobs/view/[^?]+)$", path)
        if not m:
            return link  # not a job-view URL; leave verbatim (still not invented)
        qs = [
            (k, v) for k, v in parse_qsl(u.query) if k.lower() not in _TRACKING_PARAMS
        ]
        new_query = urlencode(qs)
        return urlunparse((u.scheme, u.netloc.lower(), m.group(1), "", new_query, ""))
    except Exception:
        return link


# ---------------------------------------------------------------------------
# 2. Location parse
# ---------------------------------------------------------------------------
def parse_location(
    raw: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not raw:
        return None, None, None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return None, None, None
    country_raw = parts[-1].lower()
    country = COUNTRY_ISO.get(country_raw, None)
    city_raw = parts[0].lower()
    city = CITY_GAZETTEER.get(city_raw, city_raw.upper() or None)
    state = parts[1].upper() if len(parts) >= 3 else None
    return city, state, country


# ---------------------------------------------------------------------------
# 3. Workplace classification (evidence-based, negatives first)
# ---------------------------------------------------------------------------
_NEG_REMOTE = [
    "not remote",
    "no remote option",
    "no remote",
    "remote is not",
    "is not remote",
    "remote not available",
]
_NEG_ONSITE = [
    "must work from office",
    "onsite only",
    "on-site only",
    "work from office only",
    "office only",
]
_STRONG_REMOTE = [
    "fully remote",
    "100% remote",
    "remote position",
    "work from home",
    "remote - india",
    "remote-first",
    "remote work",
    "remote role",
]
_HYBRID = ["hybrid work", "hybrid position", "hybrid role", "hybrid"]
_ONSITE = [
    "on-site",
    "onsite",
    "work from office",
    "office-based",
    "based at our",
    "based in our",
    "in-office",
]


def classify_workplace(
    location: Optional[str], description: Optional[str]
) -> Tuple[str, bool]:
    """Return (workplace_type, conflict_flag). Conflict flag -> UNKNOWN."""
    text = _s(location).lower() + " " + _s(description).lower()
    # ignore 'remote' only appearing in interview-scam context (ModMed case)
    text = re.sub(
        r"remote[\s\"']+interviews?|remote[\s\"']+interview",
        "remoteinterviewtoken",
        text,
    )

    neg_remote = any(p in text for p in _NEG_REMOTE)
    neg_onsite = any(p in text for p in _NEG_ONSITE)
    strong_remote = any(p in text for p in _STRONG_REMOTE)
    hybrid = any(p in text for p in _HYBRID)
    onsite = any(p in text for p in _ONSITE)
    bare_remote = ("remote" in text) and ("remoteinterviewtoken" not in text)

    # Phase A: negative / contradictory evidence takes precedence
    if neg_remote or neg_onsite:
        # contradiction: negative remote but also explicit strong remote/onsite/hybrid
        if neg_remote and (strong_remote or onsite or hybrid):
            return "UNKNOWN", True
        if neg_onsite and (onsite or strong_remote):
            return "UNKNOWN", True
        return "ONSITE", False  # negative remote -> job is effectively onsite

    # Phase B: positive evidence
    if hybrid:
        return "HYBRID", False
    if onsite and strong_remote:
        return "UNKNOWN", True  # direct remote vs onsite conflict
    if onsite:
        return "ONSITE", False
    if strong_remote:
        return "REMOTE", False
    if bare_remote:
        return "REMOTE", False  # weak signal, no negative present

    return "UNKNOWN", False


# ---------------------------------------------------------------------------
# 4. Experience extraction (separate from seniority)
# ---------------------------------------------------------------------------
def extract_experience(
    description: Optional[str],
) -> Tuple[Optional[int], Optional[int]]:
    text = _s(description)
    if not text:
        return None, None
    # "Minimum N Year(s) Of Experience Is Required"
    m = re.search(r"minimum\s+(\d+)\s+year", text, re.IGNORECASE)
    if m:
        return int(m.group(1)), None
    # "2-5 years" / "2 to 5 years of ... experience"
    m = re.search(r"(\d+)\s*(?:-|to|–)\s*(\d+)\s+years?\s+of", text, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    # single "N years of experience"
    m = re.search(r"(\d+)\s+years?\s+of\s+professional", text, re.IGNORECASE)
    if m:
        return int(m.group(1)), None
    return None, None


# ---------------------------------------------------------------------------
# 5. Seniority (separate concept; explicit seniority_source)
# ---------------------------------------------------------------------------
def derive_seniority(seniority_level: Optional[str], title: str) -> Tuple[str, str]:
    """Return (seniority_class, seniority_source)."""
    lvl = _s(seniority_level).strip()
    key = lvl.lower().strip(".")
    if key and key not in ("not applicable", "na", ""):
        mapped = SENIORITY_LINKEDIN.get(key)
        if mapped:
            return mapped, "LINKEDIN"
        return "UNKNOWN", "LINKEDIN"
    # field unreliable -> infer from title, flagged
    t = title.lower()
    if any(k in t for k in ["principal", "lead"]):
        return "LEAD", "TITLE_INFERRED"
    if any(k in t for k in ["staff", "senior"]):
        return "SENIOR", "TITLE_INFERRED"
    if any(k in t for k in ["junior", "jr", "entry", "intern"]):
        return "JUNIOR", "TITLE_INFERRED"
    return "MID", "TITLE_INFERRED"


# ---------------------------------------------------------------------------
# 6. Salary interpretation (locked policy)
# ---------------------------------------------------------------------------
MIN_LPA = 4.0  # INR lakh per annum, minimum acceptable
PREF_LPA = 5.0  # INR lakh per annum, preferred

_LPA_YEAR = 100_000.0  # 1 LPA == 1,00,000 INR/year


def _parse_salary(salary_raw: Optional[str]) -> Dict[str, Any]:
    """Parse a salary string. Returns min/max/currency/period/available/in_lpa.

    `in_lpa` is True when the stated numbers are already in LPA units (e.g.
    "₹4.5 LPA", "₹6-8 LPA"). The raw numbers are NEVER invented; only the unit
    is interpreted so threshold checks apply to the true amount.
    """
    out = {
        "min": None,
        "max": None,
        "currency": None,
        "period": None,
        "available": False,
        "in_lpa": False,
    }
    s = _s(salary_raw)
    if not s:
        return out
    low = s.lower()
    currency = None
    if "₹" in s or "inr" in low:
        currency = "INR"
    elif "usd" in low or "$" in s:
        currency = "USD"
    elif "eur" in low or "€" in s:
        currency = "EUR"
    elif "gbp" in low or "£" in s:
        currency = "GBP"
    elif "aed" in low:
        currency = "AED"
    elif "inr" in low:
        currency = "INR"
    # else: currency left None (unidentifiable) -> caller treats as UNCLEAR
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", s.replace(",", ""))]
    if not nums:
        return out
    period = (
        "YEARLY"
        if ("/yr" in s.lower() or "per year" in s.lower() or "annually" in s.lower())
        else ("MONTHLY" if ("/mo" in s.lower() or "per month" in s.lower()) else None)
    )
    out["min"] = nums[0]
    out["max"] = nums[1] if len(nums) > 1 else None
    out["currency"] = currency
    out["period"] = period
    out["available"] = True
    # numbers stated directly in lakhs (LPA / lakh / lac) rather than absolute INR
    out["in_lpa"] = "lpa" in s.lower() or "lakh" in s.lower() or "lac" in s.lower()
    return out


def interpret_salary(parsed: Dict[str, Any]) -> str:
    """Map parsed salary to BELOW_MIN/ACCEPTABLE/PREFERRED/UNAVAILABLE/UNCLEAR.

    Threshold decision uses the MINIMUM stated salary. Boundary (per locked
    policy): <4 -> BELOW_MIN, 4..5 -> ACCEPTABLE, >5 -> PREFERRED (₹5.0 exactly
    is ACCEPTABLE). Never estimates salary from any other field.
    """
    if not parsed["available"]:
        return "UNAVAILABLE"
    if not parsed["currency"]:
        return "UNCLEAR"  # salary present but currency unidentifiable; never guess
    if parsed["currency"] != "INR":
        return "UNCLEAR"  # different currency; no INR conversion policy exists
    if parsed["period"] and parsed["period"] != "YEARLY":
        return "UNCLEAR"  # non-yearly (e.g. monthly); no annual conversion policy
    if parsed["min"] is None:
        return "UNCLEAR"
    min_lpa = parsed["min"] if parsed.get("in_lpa") else parsed["min"] / _LPA_YEAR
    if min_lpa < MIN_LPA:
        return "BELOW_MIN"
    if min_lpa <= PREF_LPA:
        return "ACCEPTABLE"
    return "PREFERRED"


# ---------------------------------------------------------------------------
# 7. Skills extraction
# ---------------------------------------------------------------------------
def extract_skills(description: Optional[str]) -> Tuple[List[str], List[str]]:
    text = _s(description)
    if not text:
        return [], []
    required: List[str] = []
    preferred: List[str] = []

    def _clean(phrase: str) -> List[str]:
        phrase = re.sub(
            r"^(proficiency in|proficient in|experience with)\s+",
            "",
            phrase,
            flags=re.IGNORECASE,
        )
        toks = re.split(r"[,;]|\band\b|\bfor\b", phrase)
        return [t.strip().lower().rstrip(".:") for t in toks if t.strip()]

    # Accenture style
    for pat, store in [
        (r"must\s+have\s+skills?\s*:\s*([^\n]+)", required),
        (r"must\s*to\s*have\s*skills?\s*:\s*([^\n]+)", required),
        (r"good\s+to\s+have\s+skills?\s*:\s*([^\n]+)", preferred),
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            store.extend(_clean(m.group(1)))

    # generic "Skills: ..." trailing list (UST, Talentien)
    m = re.search(r"\bskills?\s*:\s*([^\n]+)$", text, re.IGNORECASE | re.MULTILINE)
    if m:
        required.extend(_clean(m.group(1)))

    def _dedupe(lst: List[str]) -> List[str]:
        seen, out = set(), []
        for t in lst:
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out

    return _dedupe(required), _dedupe(preferred)


# ---------------------------------------------------------------------------
# 8. Quality flags + eligibility
# ---------------------------------------------------------------------------
def compute_flags(rec: Dict[str, Any]) -> List[str]:
    flags = []
    desc = _s(rec.get("job_description"))
    if not desc or len(desc) < 300:
        flags.append("INCOMPLETE_DESCRIPTION")
    elif "job description summary" in desc and "tbd" in desc:
        flags.append("INCOMPLETE_DESCRIPTION")
    if not rec.get("salary_available"):
        flags.append("MISSING_SALARY")
    if rec.get("workplace_type") == "UNKNOWN":
        flags.append("MISSING_WORKPLACE_TYPE")
    if rec.get("seniority_source") in ("TITLE_INFERRED", "DESCRIPTION_INFERRED"):
        flags.append("UNRELIABLE_SENIORITY")
    if not rec.get("company_name"):
        flags.append("MISSING_COMPANY")
    if not rec.get("location"):
        flags.append("MISSING_LOCATION")
    if rec.get("_workplace_conflict"):
        flags.append("WORKPLACE_CONFLICT")
    if rec.get("_cross_contaminated"):
        flags.append("CROSS_CONTAMINATED_DESCRIPTION")
    if rec.get("_cross_company_match"):
        flags.append("CROSS_COMPANY_DESCRIPTION_MATCH")
    return flags


def compute_status(flags: List[str]) -> str:
    if "CROSS_CONTAMINATED_DESCRIPTION" in flags:
        return "SUSPECT"
    if (
        "INCOMPLETE_DESCRIPTION" in flags
        or "MISSING_COMPANY" in flags
        or "MISSING_LOCATION" in flags
    ):
        return "PARTIAL"
    return "COMPLETE"


def compute_eligibility(status: str, flags: List[str]) -> str:
    """match_eligibility contract: ELIGIBLE / REVIEW / BLOCKED.

    NOTE (documented assumption): UNRELIABLE_SENIORITY, MISSING_SALARY and
    MISSING_WORKPLACE_TYPE are recorded as flags but do NOT force REVIEW, since
    they are extremely common on LinkedIn and would otherwise route ~all records
    to review. They affect scoring confidence in Phase 2C instead.
    """
    if status == "SUSPECT":
        return "BLOCKED"
    review_triggers = {
        "INCOMPLETE_DESCRIPTION",
        "MISSING_COMPANY",
        "MISSING_LOCATION",
        "CROSS_COMPANY_DESCRIPTION_MATCH",
        "WORKPLACE_CONFLICT",
    }
    if review_triggers & set(flags):
        return "REVIEW"
    return "ELIGIBLE"


# ---------------------------------------------------------------------------
# 9. Fingerprint + cross-company detection
# ---------------------------------------------------------------------------
def content_fingerprint(company: str, title: str, location: str, desc_norm: str) -> str:
    payload = "|".join([company.lower(), title.lower(), location.lower(), desc_norm])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def desc_fingerprint(desc_norm: str) -> str:
    """Description-only fingerprint (company-independent) for cross-company checks."""
    return hashlib.sha256(desc_norm.encode("utf-8")).hexdigest()


# tokens of a company name that are distinctive enough to assert "this text names
# this company". Avoids generic words like 'stage'/'solutions'/'india'/'ltd'.
_STOPWORDS = {
    "the",
    "and",
    "of",
    "co",
    "pvt",
    "ltd",
    "inc",
    "private",
    "limited",
    "technologies",
    "solutions",
    "software",
    "services",
    "systems",
    "india",
    "group",
    "global",
    "stage",
    "capital",
    "corp",
    "company",
    "consulting",
    "technology",
    "tech",
}


def _distinctive_tokens(company_name: str) -> List[str]:
    toks = [t for t in re.split(r"[^a-z0-9]+", company_name.lower()) if t]
    return [t for t in toks if len(t) >= 5 and t not in _STOPWORDS] or [
        company_name.lower()
    ]


def detect_cross_company(records: List[Dict[str, Any]]) -> None:
    """Two-tier cross-company handling.

    - Exact description fingerprint shared by records with DIFFERENT companies:
      the record whose description names a company other than its own is
      CROSS_CONTAMINATED_DESCRIPTION (SUSPECT/BLOCKED).
      Records sharing a template but not misattributed get
      CROSS_COMPANY_DESCRIPTION_MATCH (informational/review only).
    """
    desc_to_records: Dict[str, List[int]] = {}
    for i, r in enumerate(records):
        desc_to_records.setdefault(r["_desc_only_fp"], []).append(i)

    for fp, idxs in desc_to_records.items():
        if len(idxs) < 2:
            continue
        companies = {records[i]["company_name"].lower() for i in idxs}
        if len(companies) < 2:
            continue  # same template, same company -> not a cross-company case
        # index of the OTHER companies' distinctive tokens per record
        for i in idxs:
            r = records[i]
            desc = (r["job_description"] or "").lower()
            own = r["company_name"].lower()
            mentioned_other = False
            for j in idxs:
                if j == i:
                    continue
                other = records[j]["company_name"]
                tokens = _distinctive_tokens(other)
                if any(t in desc for t in tokens):
                    mentioned_other = True
                    break
            if mentioned_other:
                # description names a company other than the attributed one
                r["_cross_contaminated"] = True
            else:
                r["_cross_company_match"] = True


# ---------------------------------------------------------------------------
# 10. Main normalization
# ---------------------------------------------------------------------------
def normalize(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_items):
        link = _s(raw.get("link")) or _s(raw.get("applyUrl"))
        job_id = extract_job_id(link)
        city, state, country = parse_location(raw.get("location"))
        desc_norm = _norm_desc(raw.get("descriptionText"))
        wp, conflict = classify_workplace(
            raw.get("location"), raw.get("descriptionText")
        )

        parsed_salary = _parse_salary(raw.get("salary"))
        exp_min, exp_max = extract_experience(raw.get("descriptionText"))
        seniority_class, seniority_source = derive_seniority(
            raw.get("seniorityLevel"), _s(raw.get("title"))
        )
        req_skills, pref_skills = extract_skills(raw.get("descriptionText"))

        rec: Dict[str, Any] = {
            "job_id": str(uuid.uuid5(NAMESPACE, f"{SOURCE}:{job_id or idx}:{idx}")),
            "source": SOURCE,
            "source_job_id": job_id,
            "canonical_url": normalize_url(link),
            "company_name": _s(raw.get("companyName")),
            "company_url": _s(raw.get("companyLinkedinUrl")) or None,
            "job_title": _s(raw.get("title")),
            "location": _s(raw.get("location")),
            "normalized_city": city,
            "normalized_state": state,
            "country": country,
            "workplace_type": wp,
            "employment_type": (
                "FULL_TIME"
                if _s(raw.get("employmentType")).lower().startswith("full")
                else (_s(raw.get("employmentType")) or None)
            ),
            "posted_date": _s(raw.get("postedAt")) or None,
            "discovered_date": DISCOVERED_DATE,
            "salary_min": parsed_salary["min"],
            "salary_max": parsed_salary["max"],
            "salary_currency": parsed_salary["currency"],
            "salary_period": parsed_salary["period"],
            "salary_available": parsed_salary["available"],
            "salary_interpretation": interpret_salary(parsed_salary),
            "applicant_count": (
                int(_s(raw.get("applicantsCount")))
                if _s(raw.get("applicantsCount"))
                else None
            ),
            "required_experience_min": exp_min,
            "required_experience_max": exp_max,
            "seniority_class": seniority_class,
            "seniority_source": seniority_source,
            "job_description": desc_norm or None,
            "required_skills": req_skills,
            "preferred_skills": pref_skills,
            # internal-only scratch
            "_desc_fingerprint": content_fingerprint(
                _s(raw.get("companyName")),
                _s(raw.get("title")),
                _s(raw.get("location")),
                desc_norm,
            ),
            "_desc_only_fp": desc_fingerprint(desc_norm),
            "_workplace_conflict": conflict,
            "_cross_contaminated": False,
            "_cross_company_match": False,
            "_idx": idx,
        }
        rec["source_payload_reference"] = f"apify/dataset:{DATASET_ID}/item:{idx}"

        # quality
        rec["data_quality_flags"] = []
        rec["data_quality_status"] = ""
        rec["duplicate_status"] = "UNIQUE"
        rec["duplicate_of"] = None
        rec["_cluster_id"] = None
        rec["match_eligibility"] = ""
        records.append(rec)

    # cross-company detection across the batch
    detect_cross_company(records)

    # fill quality fields
    for r in records:
        r["data_quality_flags"] = compute_flags(r)
        r["data_quality_status"] = compute_status(r["data_quality_flags"])
        r["match_eligibility"] = compute_eligibility(
            r["data_quality_status"], r["data_quality_flags"]
        )
    return records


# ---------------------------------------------------------------------------
# 11. Deduplication
# ---------------------------------------------------------------------------
def deduplicate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic 4-tier dedup. Returns dict of {cluster_id: info} and mutates records."""
    clusters: Dict[Tuple, int] = {}  # key -> cluster_id
    cluster_meta: Dict[int, Dict[str, Any]] = {}
    next_cid = 0

    def key_priority(r: Dict[str, Any]) -> List[Tuple[str, Any]]:
        keys = []
        if r["source_job_id"]:
            keys.append(("source_job_id", r["source_job_id"]))
        if r["canonical_url"]:
            keys.append(("canonical_url", r["canonical_url"]))
        if r["canonical_url"]:
            # url_normalized == canonical_url here (tracking params already stripped);
            # include a dedupe-friendly fingerprint variant to honor tier-4 ordering
            keys.append(("url_normalized", r["canonical_url"]))
        keys.append(("content_fingerprint", r["_desc_fingerprint"]))
        return keys

    for r in records:
        matched = None
        for ktype, kval in key_priority(r):
            if kval is None:
                continue
            key = (ktype, kval)
            if key in clusters:
                matched = clusters[key]
                r["_match_key"] = f"{ktype}:{kval}"
                break
        if matched is None:
            cid = next_cid
            next_cid += 1
            clusters[
                (
                    ("source_job_id" if r["source_job_id"] else "url"),
                    r["source_job_id"] or r["canonical_url"] or r["_desc_fingerprint"],
                )
            ] = cid
            # ensure all keys map to this cluster for future records
            for ktype, kval in key_priority(r):
                if kval is not None:
                    clusters[(ktype, kval)] = cid
            cluster_meta[cid] = {
                "match_key": "NEW",
                "members": [r["job_id"]],
                "keys": [k[1] for k in key_priority(r) if k[1]],
            }
            r["_cluster_id"] = cid
            r["_match_key"] = "NEW"
        else:
            r["_cluster_id"] = matched
            cluster_meta[matched]["members"].append(r["job_id"])

    # survivor selection per cluster
    def quality(r: Dict[str, Any]) -> int:
        score = 0
        if r["data_quality_status"] == "COMPLETE":
            score += 3
        if r["company_name"]:
            score += 2
        if r["workplace_type"] != "UNKNOWN":
            score += 1
        if r["salary_available"]:
            score += 1
        if r["applicant_count"] is not None:
            score += 1
        if "CROSS_CONTAMINATED_DESCRIPTION" in r["data_quality_flags"]:
            score -= 5
        return score

    for cid, meta in cluster_meta.items():
        members = [r for r in records if r["_cluster_id"] == cid]
        members.sort(
            key=lambda r: (
                quality(r),
                str(r["source_job_id"] or ""),
                str(r["canonical_url"] or ""),
            ),
            reverse=True,
        )
        survivor = members[0]
        survivor["duplicate_status"] = "UNIQUE" if len(members) == 1 else "PRIMARY"
        survivor["duplicate_of"] = None
        for m in members[1:]:
            m["duplicate_status"] = "DUPLICATE"
            m["duplicate_of"] = survivor["job_id"]
        meta["survivor"] = survivor["job_id"]
        meta["count"] = len(members)
        meta["survivor_reason"] = (
            "sole member"
            if len(members) == 1
            else f"highest quality score {quality(survivor)}; tie-break by job_id/url"
        )

    return cluster_meta


# ---------------------------------------------------------------------------
# 12. Post-processing: DUPLICATE_CONTENT flag for near-identical templates
# ---------------------------------------------------------------------------
def flag_duplicate_content(records: List[Dict[str, Any]]) -> None:
    from collections import Counter

    fp_count = Counter(r["_desc_fingerprint"] for r in records)
    for r in records:
        if (
            fp_count[r["_desc_fingerprint"]] >= 3
            and "DUPLICATE_CONTENT" not in r["data_quality_flags"]
        ):
            r["data_quality_flags"].append("DUPLICATE_CONTENT")


# ---------------------------------------------------------------------------
# 13. Public output (strip internal scratch)
# ---------------------------------------------------------------------------
def public_record(r: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in r.items() if not k.startswith("_")}
    out.pop("data_quality_flags", None)
    # reinsert flags as a normal field
    out["data_quality_flags"] = r["data_quality_flags"]
    out["dedup_cluster_id"] = r["_cluster_id"]
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_items = json.load(open(INPUT_RAW))["items"]

    records = normalize(raw_items)
    clusters = deduplicate(records)
    flag_duplicate_content(records)

    # write raw preservation copy (source of truth, never deleted)
    with open(OUT_DIR / "raw_records.jsonl", "w") as f:
        for raw in raw_items:
            f.write(json.dumps(raw) + "\n")
    with open(OUT_DIR / "job_records.json", "w") as f:
        json.dump([public_record(r) for r in records], f, indent=2)
    with open(OUT_DIR / "dedup_clusters.json", "w") as f:
        json.dump(clusters, f, indent=2)

    # stats
    stats = {
        "raw_records": len(raw_items),
        "canonical_records": len(records),
        "duplicates": sum(1 for r in records if r["duplicate_status"] == "DUPLICATE"),
        "unique_or_primary": sum(
            1 for r in records if r["duplicate_status"] in ("UNIQUE", "PRIMARY")
        ),
        "status": {
            s: sum(1 for r in records if r["data_quality_status"] == s)
            for s in ("COMPLETE", "PARTIAL", "SUSPECT")
        },
        "eligibility": {
            e: sum(1 for r in records if r["match_eligibility"] == e)
            for e in ("ELIGIBLE", "REVIEW", "BLOCKED")
        },
        "clusters": {str(cid): meta["count"] for cid, meta in clusters.items()},
    }
    with open(OUT_DIR / "stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    print("=== PHASE 2B DRY RUN COMPLETE ===")
    print(json.dumps(stats, indent=2))
    print(f"\nOutputs written to: {OUT_DIR}")


if __name__ == "__main__":
    main()

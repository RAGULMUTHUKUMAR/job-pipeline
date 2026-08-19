# Scoring Model

Describes the scoring model: the **locked** component dimensions (frozen, values
are authoritative) and the **approved/implemented** composite weighting. Locked
values come directly from the frozen Phase 2B/2C modules and outputs.

> **Invariant (all dimensions):** a score ranks/deprioritizes only. `*_blocks`
> is always `false` and `*_rejection_reason` is always `null`. No dimension ever
> becomes an eligibility rejection. (ADR-001.)

---

## 1. Component scores (FROZEN — authoritative)

Each component emits a score on `[-1.0, 1.0]` (0.0 = neutral), a confidence on
`[0,1]`, and a `*_weight` (nominal, documentation-only).

| Component      | Score mapping                                                               | Confidence                                                   | Weight (nominal) | Never blocks/rejects |
| -------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------ | ---------------- | -------------------- |
| **Salary**     | PREFERRED 1.0, ACCEPTABLE 0.5, BELOW_MIN −1.0, UNAVAILABLE 0.0, UNCLEAR 0.0 | UNAVAILABLE 1.0, UNCLEAR 0.5                                 | 0.15             | yes                  |
| **Experience** | PREFERRED 1.0, ACCEPTABLE 0.5, BELOW_MIN −1.0, UNAVAILABLE 0.0, UNCLEAR 0.0 | UNAVAILABLE 1.0, UNCLEAR 0.5                                 | 0.20             | yes                  |
| **Skills**     | EXCELLENT 1.0, GOOD 0.75, PARTIAL 0.5, WEAK 0.25, NONE 0.0, UNCLEAR 0.0     | EXCELLENT/GOOD 1.0, PARTIAL/WEAK 0.75, NONE 1.0, UNCLEAR 0.5 | 0.30             | yes                  |
| **Role**       | STRONG 1.0, GOOD 0.6, GENERAL 0.5, LOW −0.5, UNCLEAR 0.0                    | STRONG/GOOD/GENERAL/LOW 1.0, UNCLEAR 0.5                     | 0.15             | yes                  |
| **Location**   | PREFERRED 1.0, ACCEPTABLE 0.5, UNAVAILABLE 0.0, UNCLEAR 0.0                 | PREFERRED/ACCEPTABLE 1.0, UNAVAILABLE 1.0, UNCLEAR 0.5       | 0.10             | yes                  |
| **Workplace**  | REMOTE 1.0, HYBRID 0.5, ONSITE 0.0, UNKNOWN 0.0                             | REMOTE/HYBRID/ONSITE 1.0, UNKNOWN 0.5                        | 0.10             | yes                  |

### 1.1 Salary (frozen)

- `PREFERRED = +1.0`, `ACCEPTABLE = +0.5`, `BELOW_MIN = -1.0` (deprioritize only),
  `UNAVAILABLE = 0.0` (neutral), `UNCLEAR = 0.0` (neutral, conf 0.5).
- Thresholds (Phase 2B): `MIN_LPA = 4.0`, `PREF_LPA = 5.0`; boundary `4..5 =
ACCEPTABLE`, `>5 = PREFERRED`, `<4 = BELOW_MIN`. Non-INR or non-yearly →
  `UNCLEAR`.
- **Salary can never reject/block.**

### 1.2 Experience (frozen)

- Target band **2–3 years**. `<2` → `BELOW_MIN` (−1.0), `2–3` → `ACCEPTABLE`
  (+0.5), `>3` → `PREFERRED` (+1.0), missing → `UNAVAILABLE` (0.0), non-numeric →
  `UNCLEAR` (0.0, conf 0.5).
- Ranges classified by **band midpoint**: `(1,2)→BELOW_MIN`, `(2,3)→ACCEPTABLE`,
  `(3,5)→PREFERRED`, `(5,None)→PREFERRED`.
- **Experience can never reject/block.**

### 1.3 Skills (frozen)

- Profile: **Tier 1 (1.0)** JavaScript, React, React Native, Node.js · **Tier 2
  (0.7)** Tailwind CSS, MongoDB, SQL, REST API, Microservices, Docker, AWS,
  AWS IAM, AWS S3 · **Tier 3 (0.4)** Golang, DSA.
- Required match = full weight; preferred match = 0.5×.
- Classification: `≥2.5=EXCELLENT(1.0)`, `≥1.5=GOOD(0.75)`, `≥0.7=PARTIAL(0.5)`,
  `≥0.25=WEAK(0.25)`, else `NONE(0.0)`; no evidence = `UNCLEAR(0.0, conf 0.5)`.
- Conservative normalization prevents false matches (`Java≠JavaScript`,
  `React≠React Native`, `Kubernetes≠Docker`, `Azure/GCP≠AWS`, `MongoDB≠SQL`,
  `REST≠GraphQL`).
- **Skills can never reject/block.**

### 1.4 Role (frozen)

- PRIMARY → STRONG `+1.0` (Frontend, React, React Native, JavaScript, Node.js,
  Full Stack, MERN). SECONDARY → GOOD `+0.6` (Software/Web/Application/Backend/
  Mobile/Node.js Backend). GENERAL `+0.5` (generic software role). LOW `−0.5`
  (Java/Python/.NET/C#/C++/DevOps/Data/ML/QA/Test/SAP/Salesforce/Mainframe).
  UNCLEAR `0.0` (conf 0.5).
- Seniority words never affect fit; a LOW specialization takes precedence over
  generic engineer/developer words.
- **Role can never reject/block.**

### 1.5 Location (implemented)

- **PREFERRED = +1.0** — Major tech hubs (BENGALURU, HYDERABAD, CHENNAI, MUMBAI, PUNE, GURGAON, NOIDA, DELHI)
- **ACCEPTABLE = +0.5** — Other Indian cities with tech presence (COIMBATORE, THIRUVANANTHAPURAM, KOCHI, KOLKATA, AHMEDABAD, VADODARA, JAIPUR, INDORE, NAGPUR, LUCKNOW, BHUBANESWAR, VISAKHAPATNAM, MYSORE)
- **UNAVAILABLE = 0.0** — Missing location data, or non-India country
- **UNCLEAR = 0.0 (conf 0.5)** — Unrecognized city/state in India
- **Location NEVER rejects/blocks.** `location_blocks=false`, `location_rejection_reason=null` on all records.
- Weight: 0.10

### 1.6 Workplace (implemented)

- **REMOTE = +1.0** — Remote / Work From Home / WFH / Fully Remote / Distributed
- **HYBRID = +0.5** — Hybrid / Hybrid Remote / Partial Remote / Flexible
- **ONSITE = 0.0** — Onsite / On-site / On Site / Office / In Office (neutral)
- **UNKNOWN = 0.0 (conf 0.5)** — Unknown / missing workplace type
- **Workplace NEVER rejects/blocks.** `workplace_blocks=false`, `workplace_rejection_reason=null` on all records.
- Weight: 0.10

---

## 2. Composite weighting (six components APPROVED / implemented)

The implemented total:

| Dimension  | Weight   | Status                     |
| ---------- | -------- | -------------------------- |
| Skills     | 0.30     | **APPROVED / implemented** |
| Experience | 0.20     | **APPROVED / implemented** |
| Role       | 0.15     | **APPROVED / implemented** |
| Salary     | 0.15     | **APPROVED / implemented** |
| Location   | 0.10     | **APPROVED / implemented** |
| Workplace  | 0.10     | **APPROVED / implemented** |
| **Total**  | **1.00** | —                          |

**Implemented (approved):** `phase2b/phase2c_composite_score.py` combines the six
locked components with weights salary 0.15 / experience 0.20 / skills 0.30 /
role 0.15 / location 0.10 / workplace 0.10. `implemented_weight = 1.00`, `reserved_weight = 0.00`.

**Composite formula (deterministic):**
`composite_score = salary_w·salary_score + experience_w·experience_score + skill_w·skill_score + role_w·role_score + location_w·location_score + workplace_w·workplace_score`
Each `weight·component_score` is stored as a `*_contribution` for auditability.

**Composite confidence (deterministic):** weighted average of the six component confidences, normalized by implemented weight (1.00):
`composite_confidence = Σ(weight_i·confidence_i) / 1.00`. On `[0,1]`. It never
feeds back into the score, so missing/unclear data can only lower confidence,
never the score. Frozen confidence semantics apply: `UNAVAILABLE → 1.0` (neutral,
no penalty), `UNCLEAR → 0.5`.

**Invariants (hard-validated):** composite never blocks (`composite_blocks=false`)
or rejects (`composite_rejection_reason=null`); `match_eligibility` and
`data_quality_status` are carried through unchanged; 1:1 join on `job_id`; 20
inputs → 20 outputs, no duplicate `job_id`; deterministic output.

---

## 5. Ranking, recommendation tiers & application decision (APPROVED / implemented)

- **Composite output:** `phase2b/output/phase2c_composite_scores.json` carries a
  per-job `composite_score`, `composite_confidence`, and `recommendation_tier`
  (implemented by `phase2b/phase2c_composite_score.py`).
- **Recommendation tier — APPROVED (deterministic score bands, 2026-08-11):**

  | Tier        | Band                             |
  | ----------- | -------------------------------- |
  | `RECOMMEND` | `composite_score >= 0.25`        |
  | `CONSIDER`  | `0.10 <= composite_score < 0.25` |
  | `MONITOR`   | `composite_score < 0.10`         |

  Current 20-record dataset split: RECOMMEND 7 / CONSIDER 8 / MONITOR 5.

- **Tiers are recommendation-only.** They never filter or reject: every job stays
  eligible/visible regardless of tier. `composite_blocks=false` and
  `composite_rejection_reason=null` on all records. Tiers may drive the future
  application decision (ADR-010) but are not an eligibility gate.
- **Ranking — APPROVED / implemented** (`phase2b/phase2c_ranking.py` →
  `output/phase2c_rankings.json`): all 20 jobs ordered by **descending
  `composite_score`**, tie-broken by **ascending `job_id`** (deterministic,
  stable). Rank 1 = highest. No job is dropped or filtered; ranking never
  blocks/rejects (`ranking_blocks=false`, `ranking_rejection_reason=null`);
  `match_eligibility` and `data_quality_status` are carried through unchanged.
- **Application decision — APPROVED / implemented** (`phase2b/phase2c_application_decision.py`
  → `output/phase2c_application_decisions.json`): a per-job application decision
  derived from the ranking. Approved **inclusive** policy:
  `CANDIDATE = match_eligibility == ELIGIBLE AND recommendation_tier in {RECOMMEND, CONSIDER}`;
  `match_eligibility == REVIEW → REVIEW` (human review required);
  `match_eligibility == BLOCKED → NOT_RECOMMENDED`. This is a **proposed shortlist
  only** — it never auto-submits, emails, creates accounts, or clicks Apply; a
  human approval gate precedes any application preparation (ADR-010).
- **Application preparation/submission, tracking, scheduling, observability, and
  persistence** remain **PROPOSED / NOT implemented** (Phase 3+, ADR-010).

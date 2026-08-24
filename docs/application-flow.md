# Application Flow Specification

**Status:** FOUNDATION IMPLEMENTED (state machine + persistent registry only)  
**Version:** 1.0.0  
**Date:** 2026-08-24  
**Governed by:** ADR-010 (Application automation out of scope until ranking stable)

---

## 1. Purpose

This document formally defines the **application lifecycle state machine**, **human approval requirements**, and **persistent state registry** for the job-application pipeline. It establishes the canonical contract between:

- **Phase 10** (Application Queue Preparation — `phase4_application_queue.py`)
- **Phase 11B** (Resume Selection — `phase11_resume_selection.py`)
- **Future Phase 12+** (Application Preparation — not yet implemented)
- **Future Phase 3** (Application Submission/Tracking — gated by ADR-010)

**This specification does NOT implement application preparation or submission.** It provides the state-model foundation that those future phases will consume.

---

## 2. Scope

### 2.1 In Scope (Implemented in this Foundation)

- Canonical application state definitions
- Valid state transition rules (deterministic, validated)
- Persistent local state registry (`application_state.json`)
- Human approval gate mechanism (explicit, recorded)
- Duplicate application protection
- Idempotent state transitions
- Audit trail structure
- Self-tests for all invariants

### 2.2 Explicitly Out of Scope (NOT Implemented)

- **Application preparation** (building cover letters, tailoring resumes, pre-filling forms)
- **Application submission** (browser automation, LinkedIn Apply clicks, form POSTs, API calls)
- **External job site interaction** (no network requests to job boards)
- **Email/notification sending**
- **Google Drive writes** (except Phase 9 daily orchestration queue upload)
- **Account creation / authentication**
- **Scheduling / cron jobs for application workflow**
- **Observability / metrics beyond the state registry**

---

## 3. What Is Explicitly Forbidden

The following actions are **permanently prohibited** in this foundation and any consuming code unless ADR-010 is formally superseded by explicit user approval:

| Forbidden Action                                         | Reason                           |
| -------------------------------------------------------- | -------------------------------- |
| Browser automation (Playwright, Selenium, etc.)          | ADR-010 safety gate              |
| LinkedIn "Apply" button clicks                           | ADR-010 safety gate              |
| Form submission to any job site                          | ADR-010 safety gate              |
| Email sending (SMTP, SendGrid, etc.)                     | ADR-010 safety gate              |
| Account creation on job boards                           | ADR-010 safety gate              |
| Network requests to external job sites                   | ADR-010 safety gate              |
| Google Drive file creation/modification (beyond Phase 9) | ADR-010 safety gate              |
| Silent auto-approval based on score/rank/selection       | Human approval must be explicit  |
| Modification of frozen Phase 2B/2C files                 | Compatibility contract (ADR-005) |

---

## 4. Application State Machine

### 4.1 Canonical States

```
DISCOVERED
    ↓
ELIGIBLE
    ↓
REVIEW
    ↓
RECOMMENDED
    ↓
APPROVED          ←── HUMAN APPROVAL GATE (explicit, recorded)
    ↓
PREPARING
    ↓
READY_TO_SUBMIT
    ↓
SUBMITTED
```

### 4.2 Terminal / Exception States

```
WITHDRAWN    — User explicitly withdrew before submission
REJECTED     — Employer rejected after submission
FAILED       — Technical failure during preparation/submission
DUPLICATE    — Duplicate application detected (blocked by duplicate guard)
```

### 4.3 State Definitions

| State             | Description                                                                                    | Source of Truth                       | Requires Human Action                   |
| ----------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------- | --------------------------------------- |
| `DISCOVERED`      | Job ingested from Apify/source, not yet normalized                                             | Phase 2B ingestion                    | No                                      |
| `ELIGIBLE`        | Passed Phase 2B eligibility (ELIGIBLE)                                                         | `match_eligibility == "ELIGIBLE"`     | No                                      |
| `REVIEW`          | Phase 2B flagged for review (`match_eligibility == "REVIEW"`) OR application decision = REVIEW | Phase 2B or Phase 2C decision         | Yes (human review)                      |
| `RECOMMENDED`     | Phase 2C application decision = CANDIDATE (ELIGIBLE + RECOMMEND/CONSIDER tier)                 | `application_decision == "CANDIDATE"` | No (automated recommendation)           |
| `APPROVED`        | **Explicit human approval recorded** — user consented to prepare this application              | `approval_record.present == true`     | **YES — explicit approval required**    |
| `PREPARING`       | Application package being built (cover letter, tailored resume, answers)                       | Future Phase 12                       | No (automated, but only after APPROVED) |
| `READY_TO_SUBMIT` | Package complete, awaiting final submission checkpoint                                         | Future Phase 12/3                     | Yes (final checkpoint)                  |
| `SUBMITTED`       | Application successfully submitted to employer                                                 | Future Phase 3                        | No (terminal success)                   |
| `WITHDRAWN`       | User withdrew before submission                                                                | User action                           | Yes                                     |
| `REJECTED`        | Employer rejected post-submission                                                              | External signal                       | N/A                                     |
| `FAILED`          | Technical error in preparation/submission pipeline                                             | System error                          | N/A                                     |
| `DUPLICATE`       | Duplicate application detected for same job/canonical_url                                      | Duplicate guard                       | N/A                                     |

---

## 5. State Transition Rules

### 5.1 Valid Transitions (Deterministic)

```
DISCOVERED   → ELIGIBLE           (Phase 2B eligibility = ELIGIBLE)
DISCOVERED   → REVIEW             (Phase 2B eligibility = REVIEW)
DISCOVERED   → NOT_RECOMMENDED    (Phase 2B eligibility = BLOCKED → terminal)

ELIGIBLE     → REVIEW             (Human flags for review)
ELIGIBLE     → RECOMMENDED        (Phase 2C decision = CANDIDATE)

REVIEW       → ELIGIBLE           (Human clears review)
REVIEW       → RECOMMENDED        (Human approves after review)
REVIEW       → WITHDRAWN          (User withdraws)

RECOMMENDED  → APPROVED           (Explicit human approval recorded)
RECOMMENDED  → REVIEW             (Human requests review)
RECOMMENDED  → WITHDRAWN          (User withdraws)

APPROVED     → PREPARING          (Future Phase 12 starts preparation)
APPROVED     → WITHDRAWN          (User withdraws approval)

PREPARING    → READY_TO_SUBMIT    (Preparation complete, all artifacts ready)
PREPARING    → FAILED             (Preparation error)
PREPARING    → WITHDRAWN          (User withdraws)

READY_TO_SUBMIT → SUBMITTED      (Future Phase 3: final checkpoint + submission)
READY_TO_SUBMIT → WITHDRAWN      (User withdraws at final checkpoint)
READY_TO_SUBMIT → FAILED         (Submission error)

SUBMITTED    → REJECTED           (Employer rejection)
SUBMITTED    → WITHDRAWN          (User withdraws after submission - rare)
```

### 5.2 Invalid Transitions (Must Reject)

- Any transition **to** `APPROVED` without explicit `approval_record.present == true`
- Any transition **to** `PREPARING` without prior `APPROVED`
- Any transition **to** `READY_TO_SUBMIT` without prior `PREPARING` completion
- Any transition **to** `SUBMITTED` without prior `READY_TO_SUBMIT`
- Any transition **from** terminal states (`SUBMITTED`, `REJECTED`, `FAILED`, `DUPLICATE`, `WITHDRAWN`)
- `DISCOVERED` → `APPROVED` (skips eligibility/decision)
- `ELIGIBLE` → `APPROVED` (skips recommendation)
- `RECOMMENDED` → `PREPARING` (skips approval)

### 5.3 Transition Validation Function

```python
def validate_transition(current: str, next: str, context: dict) -> tuple[bool, str]:
    """
    Returns (valid: bool, reason: str).
    Context must include: approval_record, phase11b_selection, etc.
    """
```

---

## 6. Human Approval Requirements

### 6.1 What Does NOT Count as Human Approval

| Signal                                       | Type                   | Counts as Approval? |
| -------------------------------------------- | ---------------------- | ------------------- |
| `selection_status == "SELECTED"` (Phase 11B) | Automated resume match | **NO**              |
| `recommendation_tier == "RECOMMEND"`         | Automated score band   | **NO**              |
| `application_decision == "CANDIDATE"`        | Automated shortlist    | **NO**              |
| High composite score (>0.5)                  | Automated ranking      | **NO**              |
| Resume skill match >80%                      | Automated matching     | **NO**              |

### 6.2 What DOES Count as Human Approval

An **explicit approval record** in the persistent state with:

```json
{
  "approval_record": {
    "present": true,
    "approved_at": "2026-08-24T10:30:00Z",
    "approved_by": "user",
    "approval_method": "cli_flag | ui_click | config_file",
    "approval_version": 1,
    "notes": "Optional user notes"
  }
}
```

### 6.3 Approval Mechanism Design

- **CLI flag**: `--approve-job <job_id>` or `--approve-all-candidates`
- **Config file**: `config/approved_applications.yaml` with job_ids
- **Interactive prompt**: Future UI/CLI integration

**The state machine MUST reject any transition to `APPROVED` if `approval_record.present != true`.**

---

## 7. Rejection Rules

### 7.1 Automated Rejection (Never Silent)

The state machine **never** silently rejects. Every rejection produces an explicit state with a reason:

| From State        | To State    | Trigger           | Recorded Reason                |
| ----------------- | ----------- | ----------------- | ------------------------------ |
| Any               | `WITHDRAWN` | User action       | `user_withdrew`                |
| `PREPARING`       | `FAILED`    | Preparation error | `preparation_error: <details>` |
| `READY_TO_SUBMIT` | `FAILED`    | Submission error  | `submission_error: <details>`  |
| `SUBMITTED`       | `REJECTED`  | Employer response | `employer_rejected`            |
| Any               | `DUPLICATE` | Duplicate guard   | `duplicate_of: <job_id>`       |

### 7.2 No Silent Filtering

- No job is dropped from the state registry
- All 15 Phase 10 candidates have a state record
- State registry is append-only (immutable history via versioning)

---

## 8. Duplicate Protection

### 8.1 Duplicate Detection Keys

A duplicate is detected if **any** of these match an existing non-terminal record:

1. **`job_id`** — Canonical Phase 2B identifier (primary)
2. **`canonical_url`** — LinkedIn job URL (secondary)
3. **`company_name` + `job_title` + `location`** — Fuzzy match (tertiary, manual review)

### 8.2 Duplicate Handling

- On detection: new record enters `DUPLICATE` state with `duplicate_of` reference
- Original record retains its state
- No automatic state change to original
- Human reviews `DUPLICATE` records periodically

### 8.3 Duplicate Guard in State Transitions

```python
def check_duplicate(job_id: str, canonical_url: str, registry: list) -> Optional[str]:
    """Returns existing record's job_id if duplicate, else None."""
```

---

## 9. Failure Handling

| Failure Point                | State Transition       | Recovery Action                             |
| ---------------------------- | ---------------------- | ------------------------------------------- |
| Phase 11B resume match fails | Stays at `RECOMMENDED` | Human assigns resume manually               |
| Preparation template error   | `PREPARING` → `FAILED` | Fix template, retry from `APPROVED`         |
| Validation error             | Stays in current state | Fix data, re-validate                       |
| State registry corruption    | N/A                    | Rebuild from Phase 10 + 11B (deterministic) |

**Key principle:** Failures are explicit state transitions, never silent drops.

---

## 10. Idempotency

### 10.1 Generation Idempotency

Running the state registry generator **twice with identical inputs** produces **byte-identical output**.

### 10.2 Transition Idempotency

Applying the same valid transition twice:

- First application: succeeds, state changes
- Second application: returns success (already in target state), no duplicate record

### 10.3 Deterministic Ordering

State registry always sorted by:

1. `rank` ascending (from Phase 2C ranking)
2. `job_id` ascending (tie-breaker)

---

## 11. Auditability

Every state record contains:

```json
{
  "job_id": "...",
  "state": "APPROVED",
  "state_version": 3,
  "state_history": [
    {"state": "DISCOVERED", "timestamp": "...", "source": "phase2b"},
    {"state": "ELIGIBLE", "timestamp": "...", "source": "phase2b"},
    {"state": "RECOMMENDED", "timestamp": "...", "source": "phase2c_decision"},
    {"state": "APPROVED", "timestamp": "...", "source": "human_approval", "approval_record": {...}}
  ],
  "phase10_queue_record": {...},
  "phase11b_selection": {...},
  "approval_record": {...},
  "duplicate_of": null,
  "created_at": "...",
  "updated_at": "..."
}
```

---

## 12. Deterministic Behavior

- All state transitions are pure functions: `(current_state, input, context) → (next_state, output)`
- No randomness, no timestamps in transition logic (timestamps only in audit trail)
- Registry generation from Phase 10 + 11B is deterministic
- Self-test: two sequential generations produce identical JSON

---

## 13. Relationship Between Phases

```
Phase 2B (Canonical Jobs, 20 records)
    ↓ eligibility: ELIGIBLE/REVIEW/BLOCKED
Phase 2C (Scoring, Ranking, Application Decision, 20 records)
    ↓ decision: CANDIDATE/REVIEW/NOT_RECOMMENDED
Phase 10 (Application Queue, 15 CANDIDATE records)
    ↓ application_status: PENDING
Phase 11B (Resume Selection, 15 records)
    ↓ selection_status: SELECTED/REVIEW/NO_MATCH
    ↓
┌──────────────────────────────────────────────────┐
│      PHASE 3 FOUNDATION: Application State       │
│                                                  │
│  application_state.json (15 records)            │
│                                                  │
│  Initial state per record:                       │
│  - ELIGIBLE + CANDIDATE + SELECTED  → RECOMMENDED│
│  - ELIGIBLE + CANDIDATE + REVIEW    → RECOMMENDED│
│  - REVIEW (any)                     → REVIEW     │
│  - BLOCKED                          → NOT_RECOMMENDED (excluded from registry)
│                                                  │
│  APPROVED requires explicit human action         │
└──────────────────────────────────────────────────┘
    ↓ (Future, after human approval)
Phase 12 (Application Preparation) → application_packages.json
    ↓
Phase 3 (Submission + Tracking)
```

---

## 14. Relationship to ADR-010

> **ADR-010**: "Application automation: out of scope until ranking is stable"
>
> - **Status**: PROPOSED (not superseded)
> - **Gate**: Explicit human approval required before any application preparation

This foundation **implements the ADR-010 gate** by:

1. Making `APPROVED` state **unreachable** without `approval_record.present == true`
2. Making `PREPARING` state **unreachable** without prior `APPROVED`
3. Documenting that `CANDIDATE`/`SELECTED`/`RECOMMEND` are **not** approval
4. Providing the persistent registry that future phases will extend

**ADR-010 remains in force.** Application submission is still NOT implemented.

---

## 15. Distinction: Preparation vs Submission

| Aspect               | Preparation (Phase 12)                                   | Submission (Phase 3)                   |
| -------------------- | -------------------------------------------------------- | -------------------------------------- |
| **What**             | Build artifacts (cover letter, tailored resume, answers) | Deliver artifacts to employer          |
| **Input**            | `APPROVED` state + job data + resume                     | `READY_TO_SUBMIT` package              |
| **Output**           | `application_packages.json`                              | `SUBMITTED` state + confirmation       |
| **Human gate**       | Start: `APPROVED` required                               | Final: `READY_TO_SUBMIT` checkpoint    |
| **Automation**       | Template filling, text generation                        | Browser/API interaction                |
| **External effects** | None (local JSON only)                                   | Network request, employer receives app |
| **Implemented**      | **NOT YET**                                              | **NOT YET**                            |

---

## 16. Persistent State Registry Schema

**File:** `phase2b/output/application_state.json`

```json
[
  {
    "job_id": "string (UUID)",
    "canonical_url": "string",
    "company_name": "string",
    "job_title": "string",
    "rank": "integer (1-15)",
    "state": "string (one of canonical states)",
    "state_version": "integer",
    "state_history": [
      {
        "state": "string",
        "timestamp": "ISO8601",
        "source": "string",
        "details": {}
      }
    ],
    "phase10_queue": {
      "application_status": "PENDING",
      "application_attempted": false,
      "application_submitted": false
    },
    "phase11b_selection": {
      "selected_resume_id": "string",
      "selected_resume": "string",
      "selection_status": "SELECTED | REVIEW | NO_MATCH",
      "selection_reason": "string"
    },
    "approval_record": {
      "present": "boolean",
      "approved_at": "ISO8601 | null",
      "approved_by": "string | null",
      "approval_method": "string | null",
      "approval_version": "integer",
      "notes": "string | null"
    },
    "duplicate_of": "string | null",
    "created_at": "ISO8601",
    "updated_at": "ISO8601"
  }
]
```

---

## 17. Initial State Mapping (Phase 10 + 11B → Foundation)

| Phase 10 `application_decision` | Phase 11B `selection_status` | Initial Foundation State                     |
| ------------------------------- | ---------------------------- | -------------------------------------------- |
| CANDIDATE                       | SELECTED                     | RECOMMENDED                                  |
| CANDIDATE                       | REVIEW                       | RECOMMENDED                                  |
| CANDIDATE                       | NO_MATCH                     | RECOMMENDED (resume gap noted)               |
| REVIEW                          | (any)                        | REVIEW                                       |
| NOT_RECOMMENDED                 | (any)                        | _(excluded from registry — not a candidate)_ |

**Note:** All 15 Phase 10 candidates have `application_decision == "CANDIDATE"`. The 4 REVIEW and 1 NOT_RECOMMENDED from Phase 2C are not in the Phase 10 queue.

---

## 18. Future Extension Points

When Phase 12 (Preparation) and Phase 3 (Submission) are implemented, they will:

1. **Read** `application_state.json` as the source of truth
2. **Transition** states via the validated transition functions
3. **Append** to `state_history` (never mutate history)
4. **Write** updated registry atomically
5. **Never** bypass the `APPROVED` gate

The registry schema is designed to be forward-compatible — new fields can be added without breaking existing consumers.

---

## 19. References

- `docs/decisions.md` — ADR-010 (Application automation gate)
- `docs/architecture.md` §9 — Application state model (design intent)
- `docs/scoring.md` §5 — Ranking, tiers, application decision
- `phase2b/phase2c_application_decision.py` — CANDIDATE/REVIEW/NOT_RECOMMENDED logic
- `phase2b/phase4_application_queue.py` — Phase 10 queue (PENDING status)
- `phase2b/phase11_resume_selection.py` — Phase 11B resume selection (SELECTED/REVIEW/NO_MATCH)
- `phase2b/application_state.py` — State machine implementation (this foundation)

---

## 20. Change Log

| Version | Date       | Author                    | Changes                         |
| ------- | ---------- | ------------------------- | ------------------------------- |
| 1.0.0   | 2026-08-24 | Foundation Implementation | Initial canonical specification |

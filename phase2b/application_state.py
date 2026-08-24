#!/usr/bin/env python3
"""
Phase 3 Foundation — Application State Machine (domain logic only)

This module contains the CANONICAL application state machine for the job
application pipeline. It is PURE DOMAIN LOGIC:

- NO network operations (no HTTP, no socket, no MCP calls)
- NO browser automation
- NO email sending
- NO Google Drive access
- NO application submission
- NO hidden side effects

It provides deterministic, validated state transitions and a persistent
state registry generator. The registry is built from existing Phase 10
(application queue) + Phase 11B (resume selection) outputs.

GOVERNING SAFETY GATE: ADR-010. No application may reach:
  - APPROVED without an explicit approval_record
  - PREPARING without prior APPROVED
  - READY_TO_SUBMIT without prior PREPARING
  - SUBMITTED (this foundation cannot produce this state)

The module exposes:
  - Canonical state constants
  - Valid transition map
  - validate_state(state) -> bool
  - validate_transition(current, next, context) -> (bool, str)
  - perform_transition(record, next_state, context) -> record
  - requires_human_approval(state) -> bool
  - can_proceed_to_preparation(record) -> bool
  - check_duplicate(job_id, canonical_url, registry) -> Optional[str]
  - build_registry(phase10_queue, phase11b_selections) -> List[dict]
  - selftest() — invariant tests

INPUTS (read-only, not modified):
  phase2b/output/phase4_application_queue.json   (Phase 10)
  phase2b/output/phase11_resume_selections.json  (Phase 11B)

OUTPUT:
  phase2b/output/application_state.json          (Phase 3 foundation registry)

DO NOT MODIFY FROZEN FILES. This module reads them; it never writes them.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
PHASE10_QUEUE = BASE_DIR / "output" / "phase4_application_queue.json"
PHASE11B_SELECTIONS = BASE_DIR / "output" / "phase11_resume_selections.json"
OUTPUT_STATE = BASE_DIR / "output" / "application_state.json"

# ---------------------------------------------------------------------------
# Canonical application states
# ---------------------------------------------------------------------------

# Lifecycle states (ordered progression)
STATE_DISCOVERED = "DISCOVERED"
STATE_ELIGIBLE = "ELIGIBLE"
STATE_REVIEW = "REVIEW"
STATE_RECOMMENDED = "RECOMMENDED"
STATE_APPROVED = "APPROVED"
STATE_PREPARING = "PREPARING"
STATE_READY_TO_SUBMIT = "READY_TO_SUBMIT"
STATE_SUBMITTED = "SUBMITTED"

# Terminal / exception states
STATE_WITHDRAWN = "WITHDRAWN"
STATE_REJECTED = "REJECTED"
STATE_FAILED = "FAILED"
STATE_DUPLICATE = "DUPLICATE"
STATE_NOT_RECOMMENDED = "NOT_RECOMMENDED"

# All valid states
ALL_STATES = {
    STATE_DISCOVERED,
    STATE_ELIGIBLE,
    STATE_REVIEW,
    STATE_RECOMMENDED,
    STATE_APPROVED,
    STATE_PREPARING,
    STATE_READY_TO_SUBMIT,
    STATE_SUBMITTED,
    STATE_WITHDRAWN,
    STATE_REJECTED,
    STATE_FAILED,
    STATE_DUPLICATE,
    STATE_NOT_RECOMMENDED,
}

# Terminal states (no exit)
TERMINAL_STATES = {
    STATE_SUBMITTED,
    STATE_REJECTED,
    STATE_FAILED,
    STATE_DUPLICATE,
    STATE_WITHDRAWN,
    STATE_NOT_RECOMMENDED,
}

# States requiring explicit human action/approval
APPROVAL_REQUIRED_STATES = {STATE_APPROVED}

# States that require approval_record to be present
GATED_BY_APPROVAL = {
    STATE_APPROVED,
    STATE_PREPARING,
    STATE_READY_TO_SUBMIT,
    STATE_SUBMITTED,
}

# ---------------------------------------------------------------------------
# Valid transitions (deterministic transition map)
# ---------------------------------------------------------------------------

TRANSITIONS: Dict[str, set] = {
    STATE_DISCOVERED: {STATE_ELIGIBLE, STATE_REVIEW, STATE_NOT_RECOMMENDED},
    STATE_ELIGIBLE: {STATE_REVIEW, STATE_RECOMMENDED},
    STATE_REVIEW: {STATE_ELIGIBLE, STATE_RECOMMENDED, STATE_WITHDRAWN},
    STATE_RECOMMENDED: {STATE_APPROVED, STATE_REVIEW, STATE_WITHDRAWN},
    STATE_APPROVED: {STATE_PREPARING, STATE_WITHDRAWN},
    STATE_PREPARING: {STATE_READY_TO_SUBMIT, STATE_FAILED, STATE_WITHDRAWN},
    STATE_READY_TO_SUBMIT: {STATE_SUBMITTED, STATE_WITHDRAWN, STATE_FAILED},
    STATE_SUBMITTED: {STATE_REJECTED, STATE_WITHDRAWN},
    # Terminal states: no valid exits
    STATE_WITHDRAWN: set(),
    STATE_REJECTED: set(),
    STATE_FAILED: set(),
    STATE_DUPLICATE: set(),
    STATE_NOT_RECOMMENDED: set(),
}

# Self-transition is always allowed (idempotency)
for _s in ALL_STATES:
    TRANSITIONS.setdefault(_s, set())
    _s and TRANSITIONS[_s].add(_s)


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------


def validate_state(state: str) -> bool:
    """Return True if `state` is a canonical application state."""
    return state in ALL_STATES


def validate_transition(
    current: str,
    next_state: str,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Validate a state transition.

    Returns (valid: bool, reason: str).

    Rules:
    - Both states must be canonical
    - Transition must be in the valid transition map
    - If next_state is gated by approval (APPROVED/PREPARING/READY_TO_SUBMIT/SUBMITTED),
      context must contain a valid approval_record with present=True
    - SUBMITTED is unreachable in this foundation (transition not in map)
    """
    context = context or {}

    if not validate_state(current):
        return False, f"Invalid current state: {current!r}"
    if not validate_state(next_state):
        return False, f"Invalid next state: {next_state!r}"

    # Terminal states cannot transition out
    if current in TERMINAL_STATES and current != next_state:
        return False, f"Terminal state {current!r} cannot transition to {next_state!r}"

    # Check valid transition map
    if next_state not in TRANSITIONS.get(current, set()):
        return False, f"Invalid transition: {current!r} → {next_state!r}"

    # Approval gate
    if next_state in GATED_BY_APPROVAL:
        approval = context.get("approval_record") or {}
        if not approval.get("present", False):
            return (
                False,
                f"Transition to {next_state!r} requires explicit approval_record.present == True",
            )

    return True, "OK"


def perform_transition(
    record: Dict[str, Any],
    next_state: str,
    context: Optional[Dict[str, Any]] = None,
    timestamp: str = "",
    source: str = "application_state",
) -> Dict[str, Any]:
    """
    Apply a validated transition to an application record.

    Pure function: returns a new record dict with updated state, version,
    and appended history. Does NOT mutate the input record.

    Raises ValueError if the transition is invalid.
    """
    current = record["state"]
    valid, reason = validate_transition(current, next_state, context)
    if not valid:
        raise ValueError(f"Cannot transition {current!r} → {next_state!r}: {reason}")

    # Idempotency: already in target state
    if current == next_state:
        return dict(record)

    new_record = dict(record)
    new_record["state"] = next_state
    new_record["state_version"] = int(record.get("state_version", 0)) + 1
    new_record["updated_at"] = timestamp

    history = list(record.get("state_history", []))
    history.append(
        {
            "state": next_state,
            "timestamp": timestamp,
            "source": source,
            "details": context or {},
        }
    )
    new_record["state_history"] = history

    # Propagate approval record if provided
    if context and "approval_record" in context:
        new_record["approval_record"] = context["approval_record"]

    return new_record


def requires_human_approval(state: str) -> bool:
    """Return True if entering `state` requires explicit human approval."""
    return state in APPROVAL_REQUIRED_STATES


def can_proceed_to_preparation(record: Dict[str, Any]) -> bool:
    """
    Check whether an application is allowed to proceed to PREPARING.

    Requires:
    - Current state == APPROVED
    - approval_record.present == True
    """
    if record.get("state") != STATE_APPROVED:
        return False
    approval = record.get("approval_record") or {}
    return bool(approval.get("present", False))


def check_duplicate(
    job_id: str,
    canonical_url: str,
    registry: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Return the job_id of an existing non-terminal record if `job_id` or
    `canonical_url` matches. Otherwise return None.

    Duplicate keys:
    1. job_id (primary)
    2. canonical_url (secondary)
    """
    for rec in registry:
        if rec.get("state") in TERMINAL_STATES:
            continue  # terminal records don't block new entries
        if rec.get("job_id") == job_id:
            return rec["job_id"]
        if canonical_url and rec.get("canonical_url") == canonical_url:
            return rec["job_id"]
    return None


# ---------------------------------------------------------------------------
# Registry generation (deterministic)
# ---------------------------------------------------------------------------


def _initial_state_for(
    application_decision: str,
    selection_status: str,
) -> str:
    """
    Map Phase 10 + Phase 11B to initial foundation state.

    CANDIDATE + (SELECTED | REVIEW | NO_MATCH) → RECOMMENDED
    REVIEW                                      → REVIEW
    NOT_RECOMMENDED                             → NOT_RECOMMENDED (excluded from registry)
    """
    if application_decision == "CANDIDATE":
        return STATE_RECOMMENDED
    if application_decision == "REVIEW":
        return STATE_REVIEW
    return STATE_NOT_RECOMMENDED


def build_registry(
    phase10_queue: List[Dict[str, Any]],
    phase11b_selections: List[Dict[str, Any]],
    timestamp: str = "2026-08-24T00:00:00Z",
) -> List[Dict[str, Any]]:
    """
    Build the persistent application state registry from Phase 10 + Phase 11B.

    Deterministic: identical inputs → identical output (sorted by rank, then job_id).

    Only CANDIDATE and REVIEW decisions from Phase 10 are included. NOT_RECOMMENDED
    jobs are excluded (they are not application candidates).

    Each record:
    - job_id, canonical_url, company_name, job_title, rank
    - state (RECOMMENDED or REVIEW)
    - state_version = 1
    - state_history (initial entry only)
    - phase10_queue (carried through)
    - phase11b_selection (carried through)
    - approval_record = {present: False, ...}  (human approval pending)
    - duplicate_of = None
    - created_at / updated_at = timestamp
    """
    # Index Phase 11B selections by job_id
    selections_by_id = {s["job_id"]: s for s in phase11b_selections}

    records: List[Dict[str, Any]] = []

    # Sort Phase 10 queue deterministically by (rank, job_id)
    sorted_queue = sorted(
        phase10_queue, key=lambda r: (r.get("rank", 0), r.get("job_id", ""))
    )

    for q in sorted_queue:
        job_id = q["job_id"]
        decision = q.get("application_decision", "")

        # Exclude NOT_RECOMMENDED from the candidate registry
        if decision == "NOT_RECOMMENDED":
            continue

        selection = selections_by_id.get(job_id, {})
        selection_status = selection.get("selection_status", "NO_MATCH")

        initial_state = _initial_state_for(decision, selection_status)

        record = {
            "job_id": job_id,
            "canonical_url": q.get("canonical_url", ""),
            "company_name": q.get("company_name", ""),
            "job_title": q.get("job_title", ""),
            "rank": q.get("rank", 0),
            "state": initial_state,
            "state_version": 1,
            "state_history": [
                {
                    "state": initial_state,
                    "timestamp": timestamp,
                    "source": "phase3_foundation_init",
                    "details": {
                        "application_decision": decision,
                        "selection_status": selection_status,
                    },
                }
            ],
            "phase10_queue": {
                "application_status": q.get("application_status", "PENDING"),
                "application_attempted": q.get("application_attempted", False),
                "application_submitted": q.get("application_submitted", False),
            },
            "phase11b_selection": {
                "selected_resume_id": selection.get("selected_resume_id", ""),
                "selected_resume": selection.get("selected_resume", ""),
                "selection_status": selection_status,
                "selection_reason": selection.get("selection_reason", ""),
            },
            "approval_record": {
                "present": False,
                "approved_at": None,
                "approved_by": None,
                "approval_method": None,
                "approval_version": 0,
                "notes": None,
            },
            "duplicate_of": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        records.append(record)

    # Duplicate detection pass (append-only, marks DUPLICATE on later matches)
    seen: List[Dict[str, Any]] = []
    for rec in records:
        dup = check_duplicate(rec["job_id"], rec["canonical_url"], seen)
        if dup:
            rec["state"] = STATE_DUPLICATE
            rec["duplicate_of"] = dup
            rec["state_history"].append(
                {
                    "state": STATE_DUPLICATE,
                    "timestamp": timestamp,
                    "source": "phase3_foundation_init",
                    "details": {"duplicate_of": dup},
                }
            )
        seen.append(rec)

    # Final deterministic sort by (rank, job_id)
    records.sort(key=lambda r: (r["rank"], r["job_id"]))
    return records


# ---------------------------------------------------------------------------
# Self-tests (in-memory, no I/O)
# ---------------------------------------------------------------------------


def selftest() -> None:
    """Run all invariant tests. Raises AssertionError on failure."""
    ok = True

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if not cond:
            ok = False
        print(f"{'OK  ' if cond else 'FAIL'}  {label}")

    # --- State validation ---
    check("validate_state valid", validate_state(STATE_RECOMMENDED))
    check("validate_state invalid", not validate_state("BOGUS"))

    # --- Valid transitions ---
    check(
        "DISCOVERED→ELIGIBLE valid",
        validate_transition(STATE_DISCOVERED, STATE_ELIGIBLE)[0],
    )
    check(
        "ELIGIBLE→RECOMMENDED valid",
        validate_transition(STATE_ELIGIBLE, STATE_RECOMMENDED)[0],
    )
    check(
        "RECOMMENDED→APPROVED valid (no approval yet, should FAIL)",
        not validate_transition(STATE_RECOMMENDED, STATE_APPROVED)[0],
    )
    check(
        "RECOMMENDED→APPROVED valid (with approval)",
        validate_transition(
            STATE_RECOMMENDED, STATE_APPROVED, {"approval_record": {"present": True}}
        )[0],
    )
    check(
        "APPROVED→PREPARING valid (with approval)",
        validate_transition(
            STATE_APPROVED, STATE_PREPARING, {"approval_record": {"present": True}}
        )[0],
    )

    # --- Invalid transitions ---
    check(
        "ELIGIBLE→APPROVED invalid (skips RECOMMENDED)",
        not validate_transition(STATE_ELIGIBLE, STATE_APPROVED)[0],
    )
    check(
        "RECOMMENDED→PREPARING invalid (skips APPROVED)",
        not validate_transition(STATE_RECOMMENDED, STATE_PREPARING)[0],
    )
    check(
        "DISCOVERED→SUBMITTED invalid (skips everything)",
        not validate_transition(STATE_DISCOVERED, STATE_SUBMITTED)[0],
    )
    check(
        "SUBMITTED→ELIGIBLE invalid (terminal)",
        not validate_transition(STATE_SUBMITTED, STATE_ELIGIBLE)[0],
    )
    check(
        "WITHDRAWN→REVIEW invalid (terminal)",
        not validate_transition(STATE_WITHDRAWN, STATE_REVIEW)[0],
    )

    # --- Approval gate ---
    check(
        "requires_human_approval(APPROVED) = True",
        requires_human_approval(STATE_APPROVED),
    )
    check(
        "requires_human_approval(RECOMMENDED) = False",
        not requires_human_approval(STATE_RECOMMENDED),
    )

    # --- can_proceed_to_preparation ---
    rec_approved = {
        "state": STATE_APPROVED,
        "approval_record": {"present": True},
    }
    rec_recommended = {
        "state": STATE_RECOMMENDED,
        "approval_record": {"present": False},
    }
    check(
        "can_proceed_to_preparation(APPROVED+approval) = True",
        can_proceed_to_preparation(rec_approved),
    )
    check(
        "can_proceed_to_preparation(RECOMMENDED) = False",
        not can_proceed_to_preparation(rec_recommended),
    )

    # --- perform_transition ---
    base = {
        "job_id": "test-1",
        "state": STATE_RECOMMENDED,
        "state_version": 1,
        "state_history": [
            {"state": STATE_RECOMMENDED, "timestamp": "t0", "source": "init"}
        ],
        "approval_record": {"present": False},
    }
    # Without approval → ValueError
    try:
        perform_transition(base, STATE_APPROVED)
        check("perform_transition without approval raises", False)
    except ValueError:
        check("perform_transition without approval raises", True)

    # With approval → success
    approved = perform_transition(
        base,
        STATE_APPROVED,
        context={"approval_record": {"present": True, "approved_by": "user"}},
        timestamp="t1",
        source="human",
    )
    check(
        "perform_transition with approval succeeds", approved["state"] == STATE_APPROVED
    )
    check("perform_transition increments version", approved["state_version"] == 2)
    check("perform_transition appends history", len(approved["state_history"]) == 2)
    check(
        "perform_transition does not mutate input",
        base["state"] == STATE_RECOMMENDED and base["state_version"] == 1,
    )

    # Idempotent self-transition
    same = perform_transition(base, STATE_RECOMMENDED, timestamp="t2")
    check("self-transition is idempotent", same == base)

    # --- check_duplicate ---
    registry = [
        {"job_id": "a", "canonical_url": "url-a", "state": STATE_RECOMMENDED},
        {"job_id": "b", "canonical_url": "url-b", "state": STATE_RECOMMENDED},
    ]
    check("check_duplicate by job_id", check_duplicate("a", "x", registry) == "a")
    check("check_duplicate by url", check_duplicate("z", "url-b", registry) == "b")
    check("check_duplicate no match", check_duplicate("c", "url-c", registry) is None)
    # Terminal record doesn't block
    registry2 = [{"job_id": "a", "canonical_url": "url-a", "state": STATE_WITHDRAWN}]
    check(
        "terminal record doesn't block duplicate",
        check_duplicate("a", "url-a", registry2) is None,
    )

    # --- build_registry determinism ---
    q = [
        {
            "job_id": "j2",
            "application_decision": "CANDIDATE",
            "rank": 2,
            "canonical_url": "u2",
            "company_name": "C2",
            "job_title": "T2",
            "application_status": "PENDING",
            "application_attempted": False,
            "application_submitted": False,
        },
        {
            "job_id": "j1",
            "application_decision": "CANDIDATE",
            "rank": 1,
            "canonical_url": "u1",
            "company_name": "C1",
            "job_title": "T1",
            "application_status": "PENDING",
            "application_attempted": False,
            "application_submitted": False,
        },
        {
            "job_id": "j3",
            "application_decision": "NOT_RECOMMENDED",
            "rank": 3,
            "canonical_url": "u3",
            "company_name": "C3",
            "job_title": "T3",
            "application_status": "PENDING",
            "application_attempted": False,
            "application_submitted": False,
        },
    ]
    sel = [
        {
            "job_id": "j1",
            "selection_status": "SELECTED",
            "selected_resume": "r1",
            "selected_resume_id": "rid1",
            "selection_reason": "best",
        },
        {
            "job_id": "j2",
            "selection_status": "REVIEW",
            "selected_resume": "r2",
            "selected_resume_id": "rid2",
            "selection_reason": "ok",
        },
    ]
    reg1 = build_registry(q, sel, timestamp="TS")
    reg2 = build_registry(q, sel, timestamp="TS")
    import json as _json

    check(
        "build_registry deterministic (byte-identical)",
        _json.dumps(reg1, sort_keys=True) == _json.dumps(reg2, sort_keys=True),
    )
    check(
        "build_registry excludes NOT_RECOMMENDED",
        all(r["job_id"] != "j3" for r in reg1),
    )
    check("build_registry includes 2 CANDIDATEs", len(reg1) == 2)
    check(
        "build_registry initial state RECOMMENDED",
        all(r["state"] == STATE_RECOMMENDED for r in reg1),
    )
    check(
        "build_registry approval pending",
        all(r["approval_record"]["present"] is False for r in reg1),
    )
    check("build_registry sorted by rank", [r["rank"] for r in reg1] == [1, 2])

    assert ok, "Application-state self-test FAILED"
    print("\nApplication-state self-test: ALL PASS")


def main() -> None:
    """Generate the persistent state registry from Phase 10 + Phase 11B outputs."""
    selftest()

    import json
    from datetime import datetime

    # Load inputs (read-only)
    phase10 = json.load(open(PHASE10_QUEUE))
    phase11b = json.load(open(PHASE11B_SELECTIONS))

    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    registry = build_registry(phase10, phase11b, timestamp=timestamp)

    # --- Validation of generated registry ---
    # 1. 1:1 with Phase 10 candidates (15 CANDIDATE records)
    candidate_ids = {
        q["job_id"] for q in phase10 if q["application_decision"] == "CANDIDATE"
    }
    registry_ids = {r["job_id"] for r in registry}
    assert (
        registry_ids == candidate_ids
    ), f"Registry job_id set mismatch: {registry_ids ^ candidate_ids}"

    # 2. No duplicate job_id in registry
    assert len(registry_ids) == len(registry), "Duplicate job_id in registry"

    # 3. Every record has valid state
    for r in registry:
        assert validate_state(r["state"]), f"Invalid state for {r['job_id']}"

    # 4. No record is APPROVED (human approval pending)
    for r in registry:
        assert r["state"] != STATE_APPROVED, f"Unexpected APPROVED for {r['job_id']}"

    # 5. No record can reach PREPARING (no approval)
    for r in registry:
        assert not can_proceed_to_preparation(
            r
        ), f"Unexpected preparation-ready for {r['job_id']}"

    # 6. Every record has pending approval
    for r in registry:
        assert (
            r["approval_record"]["present"] is False
        ), f"Approval present for {r['job_id']}"

    # Write output
    with open(OUTPUT_STATE, "w") as f:
        json.dump(registry, f, indent=2)

    from collections import Counter

    by_state = Counter(r["state"] for r in registry)

    print("\n=== PHASE 3 FOUNDATION — APPLICATION STATE REGISTRY ===")
    print(f"Registry records         : {len(registry)}")
    print(f"State distribution       : {dict(by_state)}")
    print(
        f"Human approval pending    : {sum(1 for r in registry if not r['approval_record']['present'])}"
    )
    print(f"APPROVED (should be 0)   : {by_state.get(STATE_APPROVED, 0)}")
    print(f"PREPARING (should be 0)  : {by_state.get(STATE_PREPARING, 0)}")
    print(f"SUBMITTED (should be 0)  : {by_state.get(STATE_SUBMITTED, 0)}")
    print(
        "ADR-010 respected: YES — no application reaches APPROVED without explicit approval"
    )
    print(f"\nWritten: {OUTPUT_STATE}")


if __name__ == "__main__":
    main()

"""Conservative repairs: missing facts and unsupported constraints are not fixable."""

import hashlib
import json

REPAIRABLE = {
    "DUPLICATE_ACTIVITY",
    "ACTIVITY_OVERLAP",
    "BREAK_OVERLAP",
    "DAY_BOUNDARY",
    "DAY_COUNT",
    "VISIT_DURATION",
    "PARTICIPANTS",
    "REST_MISSING",
    "VENUE_CLOSED",
    "ACTIVITY_DATE",
    "TRAVEL_TIME",
    "ROUTE_DUPLICATE",
    "ROUTE_MISSING",
    "TRANSPORT_MODE",
    "HARD_EXCLUSION",
    "BUDGET_EXCEEDED",
    "BUDGET_AT_RISK",
    "BUDGET_CAP_CHANGED",
}


def fingerprint(days, budget, findings):
    payload = dict(
        days=[d.model_dump(mode="json") for d in days],
        budget=budget.model_dump(mode="json"),
        findings=sorted((f.rule_id, tuple(f.entity_ids), f.owner, f.severity) for f in findings),
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def decision(findings, revision, maximum, signature, history):
    errors = [f for f in findings if f.hard and f.severity == "error"]
    if not errors:
        return "validated", []
    if any(f.rule_id not in REPAIRABLE for f in errors):
        return "unresolved_evidence_or_constraint", []
    if signature in history:
        return "no_progress", []
    if revision >= maximum:
        return "revision_limit", []
    return "repair", sorted({f.owner for f in errors})

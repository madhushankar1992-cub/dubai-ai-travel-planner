from dubai_planner.domain.review import Outcome

STATUS_LABELS: dict[Outcome, str] = {
    "needs_input": "More information needed",
    "validated_estimate": "Validated estimate (under disclosed assumptions)",
    "partial": "Partial plan - unresolved checks",
    "infeasible": "Infeasible within available options",
    "failed": "Planning failed",
    "cancelled": "Cancelled",
}

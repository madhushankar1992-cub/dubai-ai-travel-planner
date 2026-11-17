# Release evaluation rubric

Each scenario is evaluated against the immutable request, deterministic findings,
source provenance, terminal status and bounded resource metrics. A run passes only
when its status is one of the scenario's declared outcomes and every
`validated_estimate` satisfies the `PlanResult` invariants.

Report: sample size and repetitions, outcome distribution, expected-outcome rate,
provenance completeness, revision recovery, latency, model calls/tokens, graph and
prompt versions, dataset version and failure stop reasons. Live-provider evaluation
is opt-in because it exports approved request/catalog fields and consumes account
quota. Fixture evaluation is the offline release baseline and is never represented
as model-quality evidence.

No score may convert unknown costs, unsupported accessibility, stale evidence or a
deterministic hard error into success. Cancellation, provider failure and schema
failure must be bounded and visibly distinct from a validated estimate.

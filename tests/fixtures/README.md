# Fixture policy

All monetary values in `tests/unit/test_costing.py` and supported route examples in
`tests/unit/test_planning.py` are synthetic engineering fixtures. They are never
imported into `data/curated/` or presented as Dubai recommendations.

The architecture's quantity fixture is two adults, one room for three nights at
AED 300, two AED 100 tickets, and four shared AED 40 taxi trips: AED 1,260 before
meals, fees and contingency. It tests a subtotal, not a complete-trip estimate.

`evaluation/sample-request.json` is a structured input example. Its actual local
catalog result is deliberately partial when hours, prices or routes lack evidence.

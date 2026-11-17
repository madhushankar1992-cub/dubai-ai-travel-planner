"""Selected factual snapshots from the public, read-only Fostay rate tool.

No offer tokens, page bodies, images, booking requests or runtime network calls.
"""


def add_stay_quotes(catalog, policies):
    key = "fostay-marina-20261115"
    policies.append(
        dict(
            id=key,
            owner="Fostay / hotel supplier",
            url="https://fostay.com/agents",
            reviewed_on="2026-11-15",
            approved=True,
            review_note="Public agent research endpoint and terms checked. Selected atomic quote facts only; no bulk copying or booking. Terms: https://fostay.com/terms",
            permitted_use="Attributed local factual research snapshot; no general scraping or redistribution licence claimed.",
            attribution="Fostay",
            persistence=True,
            export=True,
            max_retention_days=None,
            allowed_fields=["evidence", "prices", "accommodation"],
        )
    )
    catalog["evidence"].append(
        dict(
            id="ev-" + key,
            source_id=key,
            url="https://fostay.com/hotels/lpcdd85",
            retrieved_at="2026-11-15T00:00:00Z",
            dataset_version=catalog["dataset_version"],
            quality="known",
            attribution="Fostay live-rate response, Rove Dubai Marina",
            retention_policy_id=key,
            max_age_days=1,
            applicable_from="2026-11-20",
            applicable_to="2026-11-22",
            method="Read-only POST https://fostay.com/api/mcp tools/call get_live_rates: hotel_id=lpcdd85, checkin=2026-11-20, checkout=2026-11-23, adults=1, children=[], currency=AED. Response: 3 nights, Rover Room Marina View; all taxes/fees included, collected_by_hotel_at_checkin=0. Review-day timestamp, not exact fetch time. Observed quote only, no reserved inventory; recheck before booking.",
        )
    )
    for suffix, amount, terms in [
        (
            "flex",
            "1557",
            "Room Only; refundable until 2026-11-18T14:00:00+04:00, then cancellation charge AED 1557.",
        ),
        ("nonrefund", "1535", "Room Only; non-refundable. No free-cancellation deadline returned."),
    ]:
        entity = "rove-marina-quote-" + suffix
        catalog["accommodation"].append(
            dict(
                id=entity,
                area_id="area-dubai-marina",
                name="Rove Dubai Marina — Rover Room Marina View / " + suffix,
                max_occupancy=3,
                price_id="price-" + entity,
                availability="unknown",
                evidence_ids=["ev-" + key],
                notes="Rate response lists maximum room occupancy 3; the retained price is ONLY for one adult in one room. Other party compositions have no quote here. "
                + terms
                + " Snapshot does not reserve availability.",
            )
        )
        catalog["prices"].append(
            dict(
                id="price-" + entity,
                entity_id=entity,
                low=amount,
                high=amount,
                currency="AED",
                unit="whole_party_stay",
                status="known",
                basis="bounded",
                taxes_fees="included",
                quote_date="2026-11-15",
                applicable_from="2026-11-20",
                applicable_to="2026-11-22",
                stay_scope=dict(
                    check_in="2026-11-20",
                    check_out="2026-11-23",
                    rooms=1,
                    travelers=dict(adults=1, child_age_bands=[]),
                ),
                evidence_ids=["ev-" + key],
                reason=terms
                + " Whole three-night stay total for one adult/one room, charged online; AED 0 collected at check-in. Meals excluded. Snapshot subject to change, not a guaranteed future booking price.",
            )
        )

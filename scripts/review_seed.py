"""Small, manually checked factual update; stores no pages and makes no network calls."""

REVIEWED = "2026-11-15T00:00:00Z"


def review(catalog, policies):
    sources = {
        "kite-public-entry": (
            "Sole Mio (Kite Beach operator)",
            "https://solemio.ae/kite-beach/",
            ["prices"],
        ),
        "alseef-public-entry": (
            "Emirates Dubai Experience",
            "https://www.emirates.com/uk/english/dubai-experience/activities/1025/al-se/",
            ["prices"],
        ),
        "mall-hours": (
            "Emaar / Dubai Mall",
            "https://www.thedubaimall.com/en/plan-your-visit/opening-hours",
            ["hours"],
        ),
        "rove-jbr-room": (
            "Rove Hotels",
            "https://www.rovehotels.com/en/hotels/rove-jbr/",
            ["accommodation"],
        ),
        "rove-la-mer-room": (
            "Rove Hotels",
            "https://www.rovehotels.com/en/hotels/rove-la-mer-beach/",
            ["accommodation"],
        ),
    }
    for key, (owner, url, fields) in sources.items():
        policies.append(
            dict(
                id=key,
                owner=owner,
                url=url,
                reviewed_on="2026-11-15",
                approved=True,
                review_note="Manually checked atomic facts only; no page bodies or images retained.",
                permitted_use="Attributed local factual records; no general scraping licence claimed.",
                attribution=owner,
                persistence=True,
                export=True,
                max_retention_days=None,
                allowed_fields=["evidence", *fields],
            )
        )
        catalog["evidence"].append(
            dict(
                id="ev-" + key,
                source_id=key,
                url=url,
                retrieved_at=REVIEWED,
                dataset_version=catalog["dataset_version"],
                quality="known",
                attribution=owner,
                retention_policy_id=key,
                max_age_days=30,
                method="Official/operator page directly checked 15 November 2026. Timestamp denotes review day. Selected facts only; not live availability or a future-date guarantee.",
            )
        )
    # Refresh only sources actually fetched in this review, not the whole catalog.
    refreshed = {"frame", "rove-offer", "jumeirah-mosque"}
    for evidence in catalog["evidence"]:
        if evidence["source_id"] in refreshed:
            evidence["retrieved_at"] = REVIEWED
            evidence["max_age_days"] = 30
            evidence["method"] = (
                "Official page directly rechecked 15 November 2026; selected facts unchanged. Review-day timestamp, not exact fetch time; no live inventory."
            )
    for policy in policies:
        if policy["id"] in refreshed:
            policy["reviewed_on"] = "2026-11-15"
    for price in catalog["prices"]:
        if any(
            ref in {"ev-frame", "ev-rove-offer", "ev-jumeirah-mosque"}
            for ref in price["evidence_ids"]
        ):
            price["quote_date"] = "2026-11-15"
    for entity, source, scope in [
        (
            "kite-beach",
            "kite-public-entry",
            "Public beach entry only; parking, food, equipment, sunbeds and paid activities excluded. No swimming-time guarantee.",
        ),
        (
            "al-seef",
            "alseef-public-entry",
            "Public waterfront promenade visit only; shops, meals, cruises and paid attractions excluded.",
        ),
    ]:
        catalog["prices"][:] = [p for p in catalog["prices"] if p["entity_id"] != entity]
        catalog["prices"].append(
            dict(
                id="price-" + entity,
                entity_id=entity,
                unit="per_person",
                status="known",
                low="0",
                high="0",
                taxes_fees="included",
                age_category="all",
                quote_date="2026-11-15",
                evidence_ids=["ev-" + source],
                reason=scope,
            )
        )
    for place in catalog["places"]:
        if place["id"] == "dubai-mall":
            place["hours"] = (
                "Retail: Mon-Thu 10:00-23:00; Fri-Sun 10:00-24:00 (Asia/Dubai). Restaurant and attraction hours differ. Published weekly hours only; reconfirm exceptions."
            )
            place["field_evidence"]["hours"] = ["ev-mall-hours"]
    for stay in catalog["accommodation"]:
        if stay["id"] == "rove-jbr":
            stay.update(
                name="Rove JBR - Rover Room",
                max_occupancy=2,
                max_adults=2,
                max_children=0,
                verified_child_age_bands=[],
                evidence_ids=["ev-rove-jbr-room"],
                notes="FAQ limits the standard Rover Room to two people/two adults. Family Room is a distinct product; generic booking widget must not establish child eligibility here. Starting offer does not confirm room category or availability.",
            )
        elif stay["id"] == "rove-la-mer":
            stay.update(
                max_occupancy=3,
                max_adults=2,
                max_children=1,
                verified_child_age_bands=["6-12"],
                evidence_ids=["ev-rove-la-mer-room"],
                notes="Rover Room booking widget: two adults plus one child aged 4-16. Only the full 6-12 input band fits. No bounded price or availability established.",
            )

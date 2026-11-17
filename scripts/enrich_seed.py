"""Selected public-source facts reviewed 2026-11-05; no network or API keys."""


def enrich(catalog, policies):
    sources = {
        "alfanar-barsha-menu": (
            "Al Fanar Restaurant & Cafe",
            "https://www.alfanarrestaurant.com/menu",
            ["identity", "prices"],
        ),
        "museum-tariffs": (
            "Dubai Culture / Dubai Legislation Portal",
            "https://dlp.dubai.gov.ae/Legislation%20Reference/2024/Administrative%20Resolution%20No.%20%28256%29%20of%202024%20Approving%20Ticket%20Prices%20for%20the%20Etihad%20%26%20Shindagha%20Museum.html",
            ["identity", "prices"],
        ),
        "shindagha-visit": (
            "Al Shindagha Museum via Visit Dubai Experiences",
            "https://experiences.visitdubai.com/productDetail/84101",
            ["identity", "hours"],
        ),
        "jumeirah-mosque": (
            "Jumeirah Mosque / SMCCU",
            "https://www.jumeirahmosque.ae/mosque-visit-public/",
            ["identity", "hours", "prices"],
        ),
        "rove-marina-room": (
            "Rove Hotels",
            "https://www.rovehotels.com/en/hotels/rove-dubai-marina/",
            ["accommodation"],
        ),
    }
    for key, (owner, url, fields) in sources.items():
        policies.append(
            dict(
                id=key,
                owner=owner,
                url=url,
                reviewed_on="2026-11-05",
                approved=True,
                review_note="Selected atomic facts and original annotations only; no page bodies, images or general scraping permission.",
                permitted_use="Local manually reviewed factual catalog with attribution.",
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
                retrieved_at="2026-11-05T00:00:00Z",
                source_updated_at=None,
                dataset_version=catalog["dataset_version"],
                quality="known",
                attribution=owner,
                retention_policy_id=key,
                max_age_days=30,
                method="Public official page checked on 5 November 2026; selected facts only. Timestamp records review date, not exact retrieval time. No dated availability established.",
            )
        )

    catalog["places"].extend(
        [
            dict(
                id="alfanar-barsha",
                name="Al Fanar (Al Barsha Pond Park)",
                category="restaurant",
                area="Al Barsha",
                interests=["food"],
                visit_minutes_min=45,
                visit_minutes_max=90,
                summary="Branch shown by default in the operator menu. Selected single-person seafood product only; prices differ by branch.",
                field_evidence={
                    "identity": ["ev-alfanar-barsha-menu"],
                    "visit_duration": ["ev-editorial"],
                },
            ),
            dict(
                id="etihad-museum",
                name="Etihad Museum",
                category="attraction",
                area="Jumeirah",
                interests=["culture", "history"],
                visit_minutes_min=90,
                visit_minutes_max=150,
                summary="Museum candidate for UAE history; duration is an editorial allowance. Confirm opening and ticket eligibility.",
                field_evidence={
                    "identity": ["ev-museum-tariffs"],
                    "visit_duration": ["ev-editorial"],
                },
            ),
            dict(
                id="jumeirah-mosque",
                name="Jumeirah Mosque public visit",
                category="attraction",
                area="Jumeirah",
                interests=["culture"],
                visit_minutes_min=75,
                visit_minutes_max=120,
                hours="Saturday–Thursday: sessions at 10:00 and 14:00; registration 30 minutes earlier. Closed Friday. These are fixed sessions, not a continuous opening window.",
                summary="Guided cultural visit. No advance booking required; modest dress requested. Duration is an editorial allowance; confirm session availability.",
                field_evidence={
                    "identity": ["ev-jumeirah-mosque"],
                    "hours": ["ev-jumeirah-mosque"],
                    "visit_duration": ["ev-editorial"],
                },
            ),
        ]
    )
    for place in catalog["places"]:
        if place["id"] == "shindagha":
            place["hours"] = "Daily 10:00–20:00; last admission 19:00. Reconfirm special dates."
            place["field_evidence"]["hours"] = ["ev-shindagha-visit"]

    for entity, amount, source in [
        ("shindagha", "50", "museum-tariffs"),
        ("etihad-museum", "25", "museum-tariffs"),
        ("jumeirah-mosque", "55", "jumeirah-mosque"),
    ]:
        # Replace unknown placeholders; do not create competing unqualified prices.
        catalog["prices"][:] = [p for p in catalog["prices"] if p["entity_id"] != entity]
        catalog["prices"].append(
            dict(
                id="price-" + entity,
                entity_id=entity,
                unit="per_person",
                status="known",
                low=amount,
                high=amount,
                taxes_fees="unknown",
                age_category="adult",
                quote_date="2026-11-05",
                evidence_ids=["ev-" + source],
                reason=(
                    "Published public-visit admission including refreshments and Majlis activities; not a full meal. Confirm child eligibility and additional fees."
                    if entity == "jumeirah-mosque"
                    else "Published individual admission tariff. Student/group/trade products have separate eligibility; these discounts are not applied automatically. Confirm fees and visit-date price."
                ),
            )
        )
    for stay in catalog["accommodation"]:
        if stay["id"] == "rove-marina":
            stay.update(
                max_occupancy=3,
                max_adults=2,
                max_children=1,
                verified_child_age_bands=["6-12"],
                evidence_ids=["ev-rove-marina-room"],
                notes="Rover Room: 2 adults plus 1 child. Booking widget says ages 4–16; room description says under 16. Only the entire 6–12 input band is unambiguous; other child bands need confirmation. Room price and availability remain unconfirmed; linked starting offer is a separate product.",
            )
    catalog["prices"].append(
        dict(
            id="price-alfanar-barsha",
            entity_id="alfanar-barsha",
            unit="per_person_meal",
            status="known",
            low="78",
            high="78",
            taxes_fees="unknown",
            quote_date="2026-11-05",
            evidence_ids=["ev-alfanar-barsha-menu"],
            reason="Small Mixed Seafood BBQ, explicitly serves one person, AED 78 on the Al Barsha default menu. Selected product only, not a full-menu range; excludes additional orders. Confirm fees and branch before travel.",
        )
    )

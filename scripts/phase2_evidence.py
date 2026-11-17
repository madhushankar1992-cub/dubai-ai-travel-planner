"""Compact reviewed scenario evidence. Rebuilding is entirely offline."""

import math
from decimal import Decimal


def complete_example(catalog, policies):
    version = catalog["dataset_version"]
    sources = [
        (
            "phase2-assumptions",
            "Project planning estimates",
            "docs/phase2-example.md",
            ["prices", "hours", "routes", "tariffs"],
            "estimated",
            "Explicit opt-in planning allowances, not supplier quotes. Meal: AED 30-80 per person per meal including fees. Ticket allowance: published base to base*1.05+10, covering a provisional VAT/fee reserve. Road timing: ceil(OSRM seconds/60)+10 to twice that value+10, including access, waiting and traffic allowance. Taxi spending allowance per traveler: ceil(km*2.5+15) to ceil(km*4+35), inclusive of a provisional toll/fee reserve. None is a guaranteed maximum. Recurring opening schedules projected ONLY onto 20-23 November 2026; exceptions require reconfirmation.",
        ),
        (
            "osrm-nov15",
            "OpenStreetMap contributors / OSRM / FOSSGIS",
            "https://router.project-osrm.org/table/v1/driving/55.145,25.081;55.301,25.235;55.29,25.269;55.279,25.198;55.309,25.265?annotations=duration,distance&generate_hints=false",
            ["routes", "prices"],
            "estimated",
            "Public driving table fetched 15 November 2026; code Ok for all 25 cells, no fallback cells. Five approximate catalog coordinates; snapped distances 18.895,46.600,34.167,22.850,3.397 metres. Road connectivity between snapped points supports a taxi estimate, not exact hotel/entrance access, traffic, dispatch or accessibility. OSM data: https://www.openstreetmap.org/copyright ; ODbL https://opendatacommons.org/licenses/odbl/1-0/ . Tiny educational snapshot, no runtime API dependency.",
        ),
        (
            "alseef-hours",
            "Dubai Holding / Souk Al Seef",
            "https://soukalseef.ae/en/plan-your-visit",
            ["hours"],
            "known",
            "Operator retail hours checked 15 November 2026: Mon-Thu 10:00-22:00, Fri-Sun 10:00-23:00. Use these conservative visiting hours, not a claim of unrestricted 24-hour access.",
        ),
        (
            "mall-free",
            "Emirates Dubai Experience",
            "https://www.emirates.com/de/english/dubai-experience/activities/964/the-dubai-mal/",
            ["prices"],
            "known",
            "Emirates lists Dubai Mall as a free activity. Browsing only; purchases, parking, food and separately ticketed attractions excluded.",
        ),
        (
            "shindagha-hours-brochure",
            "Dubai Culture / Al Shindagha Museum",
            "https://alshindagha.dubaiculture.gov.ae/Documents/ASM-Brochure-English.pdf",
            ["hours"],
            "known",
            "Official brochure's indexed Plan Your Visit section checked 15 November 2026: daily 10:00-20:00. Direct PDF retrieval timed out; only indexed atomic opening fact retained, no brochure copied. Special-date exceptions unconfirmed.",
        ),
    ]
    for key, owner, url, fields, quality, method in sources:
        policies.append(
            dict(
                id=key,
                owner=owner,
                url=url,
                reviewed_on="2026-11-15",
                approved=True,
                review_note=method,
                permitted_use="Attributed atomic factual snapshot and original estimates; OSM-derived records under ODbL. No page bodies, images or general scraping rights.",
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
                retrieved_at="2026-11-15T00:00:00Z",
                dataset_version=version,
                quality=quality,
                attribution=owner,
                retention_policy_id=key,
                max_age_days=7,
                method=method,
            )
        )
    for place in catalog["places"]:
        key = place["id"]
        if key not in {"dubai-frame", "shindagha", "dubai-mall", "al-seef"}:
            continue
        source = {
            "dubai-frame": "frame",
            "shindagha": "shindagha-hours-brochure",
            "dubai-mall": "mall-hours",
            "al-seef": "alseef-hours",
        }[key]
        if key == "al-seef":
            place["hours"] = (
                "Retail Mon-Thu 10:00-22:00, Fri-Sun 10:00-23:00; conservative visiting hours."
            )
        place["field_evidence"]["hours"] = ["ev-" + source]
        place["opening_windows"] = [
            dict(
                weekday=day,
                start_minute=480 if key == "dubai-frame" else 600,
                end_minute=1260
                if key == "dubai-frame"
                else 1200
                if key == "shindagha"
                else (1380 if day < 4 else 1440)
                if key == "dubai-mall"
                else (1320 if day < 4 else 1380),
                valid_from="2026-11-20",
                valid_to="2026-11-23",
                evidence_ids=["ev-" + source, "ev-phase2-assumptions"],
                estimated=True,
            )
            for day in range(7)
        ]
    catalog["prices"][:] = [p for p in catalog["prices"] if p["entity_id"] != "dubai-mall"]
    catalog["prices"].append(
        dict(
            id="price-dubai-mall",
            entity_id="dubai-mall",
            unit="per_person",
            status="known",
            low="0",
            high="0",
            taxes_fees="included",
            age_category="all",
            quote_date="2026-11-15",
            evidence_ids=["ev-mall-free"],
            reason="Free public browsing only. Food, purchases, parking and ticketed attractions excluded.",
        )
    )
    for entity, base, source in [("dubai-frame", 50, "frame"), ("shindagha", 50, "museum-tariffs")]:
        catalog["prices"].append(
            dict(
                id="allowance-" + entity,
                requires_opt_in=True,
                entity_id=entity,
                unit="per_person",
                status="estimated",
                low=str(base),
                high=str(Decimal(base) * Decimal("1.05") + 10),
                taxes_fees="included",
                age_category="adult",
                evidence_ids=["ev-" + source, "ev-phase2-assumptions"],
                reason="OPTIONAL inclusive planning allowance: published adult base plus up to 5% VAT and AED 10 fee reserve. Not an all-in supplier quote or guaranteed upper price. Original tariff retained separately.",
            )
        )
    catalog["tariffs"].append(
        dict(
            id="meal-planning-allowance",
            name="Optional meal spending allowance",
            conditions="AED 30-80 per traveler per unpriced meal. Includes a fee reserve; no restaurant, menu, dietary suitability or availability promised.",
            evidence_ids=["ev-phase2-assumptions"],
        )
    )
    catalog["prices"].append(
        dict(
            id="price-meal-allowance",
            requires_opt_in=True,
            entity_id="meal-planning-allowance",
            unit="per_person_meal",
            status="estimated",
            low="30",
            high="80",
            taxes_fees="included",
            age_category="all",
            evidence_ids=["ev-phase2-assumptions"],
            reason="Opt-in original meal spending allowance, AED 30-80 per meal including fee reserve. Not a venue quote. Three meals daily minus separately priced restaurant visits; no breakfast credit for room-only hotel.",
        )
    )
    ids = ["area-dubai-marina", "dubai-frame", "shindagha", "dubai-mall", "al-seef"]
    distances = [
        [0, 25205.2, 28697, 20928.8, 30879.2],
        [25756, 0, 5684.1, 7496.5, 7778.1],
        [29882.1, 6407.8, 0, 11622.6, 3775.4],
        [21454.7, 6632.8, 10124.7, 0, 12306.9],
        [29812.1, 6737.3, 6223.8, 11552.7, 0],
    ]
    durations = [
        [0, 1371.2, 1466, 1165.1, 1706.8],
        [1441.1, 0, 534.2, 597.4, 718.1],
        [1668.3, 548.1, 0, 824.6, 311],
        [1251.8, 574.7, 669.5, 0, 910.3],
        [1692, 655.8, 514, 848.3, 0],
    ]
    catalog["routes"][:] = [
        r
        for r in catalog["routes"]
        if not (r["mode"] == "taxi" and r["origin_id"] in ids and r["destination_id"] in ids)
    ]
    for i, origin in enumerate(ids):
        for j, destination in enumerate(ids):
            if i == j:
                continue
            key = "road-" + origin + "-" + destination
            lower = math.ceil(durations[i][j] / 60) + 10
            method = f"OSRM driving: {distances[i][j]} metres, {durations[i][j]} seconds between approximate snapped catalog points. Duration includes access/waiting/traffic allowance; no live traffic or exact property entrance guarantee."
            catalog["routes"].append(
                dict(
                    id=key,
                    origin_id=origin,
                    destination_id=destination,
                    mode="taxi",
                    duration_min=lower,
                    duration_max=lower * 2 + 10,
                    status="estimated",
                    feasibility_supported=True,
                    includes_contingency=True,
                    price_id="price-" + key,
                    evidence_ids=["ev-osrm-nov15", "ev-phase2-assumptions"],
                    method=method,
                )
            )
            km = Decimal(str(distances[i][j])) / 1000
            catalog["prices"].append(
                dict(
                    id="price-" + key,
                    requires_opt_in=True,
                    entity_id=key,
                    unit="per_person",
                    status="estimated",
                    low=str(math.ceil(km * Decimal("2.5") + 15)),
                    high=str(math.ceil(km * 4 + 35)),
                    taxes_fees="included",
                    age_category="all",
                    evidence_ids=["ev-osrm-nov15", "ev-phase2-assumptions"],
                    reason="Per-traveler taxi spending allowance: ceil(km*2.5+15) to ceil(km*4+35). Reserves a whole car allowance per traveler, intentionally no sharing discount. Includes provisional toll/fee reserve, not a regulated fare or guaranteed maximum. "
                    + method,
                )
            )

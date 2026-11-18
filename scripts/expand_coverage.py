"""Reviewed coverage expansion (18 November 2026): hours, prices and OSRM routes for more places.

Rebuilding is entirely offline. Facts were read from the sources named below on 18 November
2026 through search-indexed pages (direct page retrieval was not performed), so every record
states its quality honestly. Where listings disagree, the conservative overlap is used and the
record is marked estimated. Bu Qtair was left out: a single unofficial listing is not enough.
"""

import json
import math
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEWED = "2026-11-18"
VALID_FROM, VALID_TO = "2026-11-20", "2026-11-26"
ASSUMPTIONS = "expanded-assumptions"

# source key -> (owner, url, quality, method)
HOURS_SOURCES = {
    "alfanar-hours": (
        "Al Fanar Restaurant",
        "https://alfanarrestaurant.com/al-seef-dubai",
        "known",
        "Official Al Seef branch page (search-indexed text, 18 November 2026): open 12:00-23:00 "
        "daily; may change on public holidays and during Ramadan.",
    ),
    "thebeach-jbr-hours": (
        "The Beach JBR",
        "https://www.thebeach.ae/en/faq",
        "known",
        "Official FAQ (search-indexed text, 18 November 2026): retail, services and entertainment "
        "Sun-Thu 10:00-23:00, Fri-Sat 10:00-24:00. The public sand is reported open 24 hours by "
        "travel sites (unconfirmed); the planning window deliberately follows The Beach's "
        "published hours.",
    ),
    "visitdubai-marina-walk": (
        "Visit Dubai",
        "https://visitdubai.com/fi/places-to-visit/marina-walk",
        "known",
        "Official Visit Dubai listing (search-indexed text, 18 November 2026): free to visit and "
        "open at all hours. Shops and restaurants keep their own hours. The 08:00-22:00 planning "
        "window is a conservative choice, not a closing time.",
    ),
    "fahidi-guides": (
        "Travel guides (Bayut, Property Finder)",
        "https://bayut.com/mybayut/guide-to-the-al-fahidi-historical-district",
        "estimated",
        "Travel-guide consensus, 18 November 2026: the neighbourhood has no official visiting "
        "hours and can be walked at any time; one summary cited a Dubai Culture listing of "
        "00:00-23:59. Museums and cafes inside keep their own hours (Dubai Museum status "
        "uncertain). The 09:00-19:00 planning window is conservative. Not confirmed directly "
        "with Dubai Culture.",
    ),
    "gold-souk-guides": (
        "Travel guides (Property Finder, Bayut)",
        "https://www.propertyfinder.ae/blog/gold-souk-dubai/",
        "estimated",
        "Third-party listings, 18 November 2026, disagree (09:00-21:00, 09:30-21:30, "
        "10:00-22:00). Most give Sat-Thu from morning and Friday from about 16:00. Conservative "
        "overlap used: Sat-Thu 10:00-21:30, Fri 16:00-21:30. Individual shops differ; some close "
        "mid-afternoon.",
    ),
    "tea-house-listings": (
        "Restaurant listings (What's On and others)",
        "https://whatson.ae/2023/09/local-legend-review-of-arabian-tea-house/",
        "estimated",
        "Third-party listings, 18 November 2026: most give 07:00-23:00 daily, others 07:30 and "
        "some weekdays to 22:00. Conservative overlap used: 07:30-22:00 daily. Official site not "
        "confirmed.",
    ),
    "khayma-listings": (
        "Restaurant listings (Visit Dubai food guide and others)",
        "https://visitdubai.com/en/articles/emirati-food-in-dubai",
        "estimated",
        "Listings, 18 November 2026, disagree (08:00-23:00 versus 09:00-22:00). Conservative "
        "overlap used: 09:00-22:00 daily. Restaurant's own site not confirmed.",
    ),
    "kite-beach-faq": (
        "Kite Beach rental and operator FAQ",
        "https://kite-beach-rentals.squarespace.com/kite-beach-faq",
        "estimated",
        "FAQ and travel guides, 18 November 2026: the beach is open 24 hours while restaurants, "
        "toilets, showers and the beach club close overnight; facility hours are commonly "
        "10:00-22:00. The planning window uses the facility hours. Operator hours not confirmed "
        "directly.",
    ),
}

# place -> (source key, {weekday (Monday=0): (start_minute, end_minute)}, hours text)
ALL = range(7)
WINDOWS = {
    "al-fanar": (
        "alfanar-hours",
        {d: (720, 1380) for d in ALL},
        "Daily 12:00-23:00 (official branch page).",
    ),
    "jbr-beach": (
        "thebeach-jbr-hours",
        {**{d: (600, 1380) for d in (0, 1, 2, 3, 6)}, **{d: (600, 1440) for d in (4, 5)}},
        "The Beach JBR hours: Sun-Thu 10:00-23:00, Fri-Sat 10:00-24:00 (public sand reported 24h).",
    ),
    "marina-walk": (
        "visitdubai-marina-walk",
        {d: (480, 1320) for d in ALL},
        "Open at all hours (Visit Dubai); planning window 08:00-22:00.",
    ),
    "al-fahidi": (
        "fahidi-guides",
        {d: (540, 1140) for d in ALL},
        "Open-air neighbourhood, no official hours; planning window 09:00-19:00.",
    ),
    "gold-souk": (
        "gold-souk-guides",
        {**{d: (600, 1290) for d in (0, 1, 2, 3, 5, 6)}, 4: (960, 1290)},
        "Sat-Thu 10:00-21:30, Fri 16:00-21:30 (listings vary; shops differ).",
    ),
    "arabian-tea-house": (
        "tea-house-listings",
        {d: (450, 1320) for d in ALL},
        "Daily 07:30-22:00 (conservative overlap of listings).",
    ),
    "al-khayma": (
        "khayma-listings",
        {d: (540, 1320) for d in ALL},
        "Daily 09:00-22:00 (conservative overlap of listings).",
    ),
    "kite-beach": (
        "kite-beach-faq",
        {d: (600, 1320) for d in ALL},
        "Beach open 24h; facilities about 10:00-22:00 (planning window).",
    ),
}
FREE_ACCESS = ("al-fahidi", "gold-souk", "jbr-beach", "marina-walk")
RESTAURANTS = ("al-fanar", "al-khayma", "arabian-tea-house")


def _policy(policies, key, owner, url, fields, method):
    policies.append(
        dict(
            id=key,
            owner=owner,
            url=url,
            reviewed_on=REVIEWED,
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


def _evidence(catalog, key, owner, url, quality, method, max_age):
    catalog["evidence"].append(
        dict(
            id="ev-" + key,
            source_id=key,
            url=url,
            retrieved_at=REVIEWED + "T00:00:00Z",
            dataset_version=catalog["dataset_version"],
            quality=quality,
            attribution=owner,
            retention_policy_id=key,
            max_age_days=max_age,
            method=method,
        )
    )


def expand_coverage(catalog, policies):
    table = json.loads(
        (ROOT / "data/curated/osrm-table-2026-11-18.json").read_text(encoding="utf-8")
    )
    snapped = ", ".join(str(s) for s in table["snapped_m"])
    osrm_method = (
        f"Public OSRM driving table fetched {table['retrieved_on']}; code {table['code']} for all "
        f"{len(table['ids']) ** 2} cells. Approximate catalog coordinates snapped by {snapped} "
        "metres. Road connectivity between snapped points supports a taxi estimate, not exact "
        "entrances, traffic, dispatch or accessibility. OSM data: "
        "https://www.openstreetmap.org/copyright ; ODbL "
        "https://opendatacommons.org/licenses/odbl/1-0/ . Static snapshot, no runtime API "
        "dependency. Bu Qtair is in the table but unused."
    )
    assumptions = (
        "Explicit opt-in planning allowances, not supplier quotes. Restaurant visit without a "
        "quote: AED 30-80 per person including a fee reserve. Road timing: ceil(OSRM "
        "seconds/60)+10 to twice that value+10. Taxi allowance per traveler: ceil(km*2.5+15) to "
        "ceil(km*4+35). Recurring opening hours projected ONLY onto 20-26 November 2026; "
        "exceptions require reconfirmation."
    )
    shared = [
        (
            "osrm-nov18",
            "OpenStreetMap contributors / OSRM / FOSSGIS",
            table["url"],
            ["routes", "prices"],
            osrm_method,
        ),
        (
            ASSUMPTIONS,
            "Project planning estimates",
            "docs/data-catalog.md",
            ["prices", "hours", "routes", "tariffs"],
            assumptions,
        ),
    ]
    for key, owner, url, fields, method in shared:
        _policy(policies, key, owner, url, fields, method)
        _evidence(catalog, key, owner, url, "estimated", method, 14)
    for key, (owner, url, quality, method) in HOURS_SOURCES.items():
        _policy(policies, key, owner, url, ["hours", "prices"], method)
        _evidence(catalog, key, owner, url, quality, method, 30)

    places = {p["id"]: p for p in catalog["places"]}
    for pid, (source, days, text) in WINDOWS.items():
        place = places[pid]
        place["hours"] = text
        place["field_evidence"]["hours"] = ["ev-" + source]
        place["opening_windows"] = [
            dict(
                weekday=day,
                start_minute=start,
                end_minute=end,
                valid_from=VALID_FROM,
                valid_to=VALID_TO,
                evidence_ids=["ev-" + source, "ev-" + ASSUMPTIONS],
                estimated=True,
            )
            for day, (start, end) in sorted(days.items())
        ]

    replaced = {*FREE_ACCESS, *RESTAURANTS}
    catalog["prices"][:] = [p for p in catalog["prices"] if p["entity_id"] not in replaced]
    for pid in FREE_ACCESS:
        catalog["prices"].append(
            dict(
                id="price-" + pid,
                entity_id=pid,
                unit="per_person",
                status="known",
                low="0",
                high="0",
                taxes_fees="included",
                age_category="all",
                quote_date=REVIEWED,
                evidence_ids=["ev-" + WINDOWS[pid][0]],
                reason="Free public access to walk or browse only. Food, purchases, parking, rentals and paid activities excluded.",
            )
        )
    for pid in RESTAURANTS:
        catalog["prices"].append(
            dict(
                id="price-" + pid,
                requires_opt_in=True,
                entity_id=pid,
                unit="per_person_meal",
                status="estimated",
                low="30",
                high="80",
                taxes_fees="included",
                age_category="all",
                evidence_ids=["ev-" + ASSUMPTIONS],
                reason="Opt-in planning allowance AED 30-80 per meal including a fee reserve. Not a menu quote; no menu, dietary suitability or availability promised.",
            )
        )

    ids = [i for i in table["ids"] if i != "bu-qtair"]
    index = {key: n for n, key in enumerate(table["ids"])}
    # The original five-point routes keep their own 15 November evidence untouched, so the
    # historical acceptance example is reproducible. Only pairs involving a new place are added.
    legacy = {"area-dubai-marina", "dubai-frame", "shindagha", "dubai-mall", "al-seef"}
    evidence = ["ev-osrm-nov18", "ev-" + ASSUMPTIONS]
    for origin in ids:
        for destination in ids:
            if origin == destination or (origin in legacy and destination in legacy):
                continue
            seconds = table["durations_s"][index[origin]][index[destination]]
            metres = table["distances_m"][index[origin]][index[destination]]
            key = "road-" + origin + "-" + destination
            lower = math.ceil(seconds / 60) + 10
            method = (
                f"OSRM driving: {metres} metres, {seconds} seconds between approximate snapped "
                "catalog points. Duration includes access/waiting/traffic allowance; no live "
                "traffic or exact entrance guarantee."
            )
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
                    evidence_ids=evidence,
                    method=method,
                )
            )
            km = Decimal(str(metres)) / 1000
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
                    evidence_ids=evidence,
                    reason="Per-traveler taxi spending allowance: ceil(km*2.5+15) to ceil(km*4+35). Reserves a whole car allowance per traveler, intentionally no sharing discount. Includes a provisional toll/fee reserve, not a regulated fare or guaranteed maximum. "
                    + method,
                )
            )

"""Rebuild manually researched seed records; never fetches websites or invents quotes."""

import json
import math
from pathlib import Path

from enrich_seed import enrich
from phase2_evidence import complete_example
from review_seed import review
from stay_quotes import add_stay_quotes

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026-11-15.2"
REVIEWED = "2026-11-05T00:00:00Z"  # Review date; exact retrieval time not retained
SOURCES = {
    "rove-offer": ("Rove Hotels", "https://www.rovehotels.com/en/offer/beach-staycation/"),
    "ravi-menu": ("Ravi Restaurants", "https://ravirestaurants.ae/menu/"),
    "editorial": ("Project editorial estimates", "docs/data-catalog.md"),
    "rta": (
        "Roads and Transport Authority",
        "https://rta.ae/wps/portal/rta/ae/public-transport/Nol-Fares",
    ),
    "frame": ("Dubai Municipality / Dubai Frame", "https://www.dubaiframe.ae/en/plan-your-visit"),
    "neighborhoods": (
        "Dubai Department of Economy and Tourism",
        "https://www.visitdubai.com/en/explore-dubai/dubai-neighbourhoods",
    ),
    "culture": (
        "Dubai Department of Economy and Tourism",
        "https://www.visitdubai.com/en/articles/dubais-top-11-cultural-locations",
    ),
    "city-guide": (
        "Dubai Department of Economy and Tourism",
        "https://www.visitdubai.com/-/media/Images/pdf/2026/dubai-city-guide-en-2026.pdf",
    ),
    "alseef": ("Souk Al Seef", "https://soukalseef.ae/en/discover/attractions"),
    "kite": (
        "Dubai Department of Economy and Tourism",
        "https://www.visitdubai.com/en/places-to-visit/kite-beach",
    ),
    "beaches": (
        "Dubai Department of Economy and Tourism",
        "https://www.visitdubai.com/en/things-to-do/beaches-in-dubai",
    ),
    "marina": (
        "Dubai Department of Economy and Tourism",
        "https://www.visitdubai.com/en/articles/a-guide-to-dubai-marina",
    ),
    "mall": ("Emaar Properties", "https://uae.emaar.com/en/dubai-mall"),
    "tea-house": (
        "Dubai Department of Economy and Tourism",
        "https://www.visitdubai.com/en/restaurants/arabian-tea-house",
    ),
    "food-tour": (
        "Dubai Department of Economy and Tourism",
        "https://www.dubaidet.gov.ae/en/newsroom/press-releases/cultural-food-tours-2026?print=",
    ),
    "satwa": (
        "Dubai Department of Economy and Tourism",
        "https://www.visitdubai.com/en/explore-dubai/dubai-neighbourhoods/satwa",
    ),
    "buqtair": (
        "Dubai Department of Economy and Tourism",
        "https://www.visitdubai.com/en/restaurants/bu-qtair",
    ),
    "alfanar": ("Souk Al Seef", "https://soukalseef.ae/en/discover/dine/al-fanar-seafood-market"),
}
FIELDS = [
    "evidence",
    "identity",
    "coordinates",
    "visit_duration",
    "hours",
    "accessibility",
    "prices",
    "routes",
    "accommodation",
    "tariffs",
    "crowd_guidance",
]
policies = []
evidence = []
for key, (owner, url) in SOURCES.items():
    policies.append(
        dict(
            id=key,
            owner=owner,
            url=url,
            reviewed_on="2026-11-05",
            approved=True,
            review_note="Manually selected factual references and original annotations only; no website text, images, reviews, menus or raw responses copied. Approval covers these authored seed fields, not scraping or a general redistribution licence.",
            permitted_use="Local factual catalog and original editorial estimates; retain attribution and uncertainty.",
            attribution=owner,
            persistence=True,
            export=True,
            max_retention_days=None,
            allowed_fields=FIELDS,
        )
    )
    evidence.append(
        dict(
            id="ev-" + key,
            source_id=key,
            url=None if key == "editorial" else url,
            local_record_id="editorial-method-v1" if key == "editorial" else None,
            retrieved_at=REVIEWED,
            source_updated_at=None,
            dataset_version=VERSION,
            quality="estimated" if key == "editorial" else "known",
            attribution=owner,
            retention_policy_id=key,
            max_age_days=30 if key in ("rta", "frame") else 180,
            method=(
                "Original estimates: approximate map centroids, visit allowances, and heuristic route ranges. Not observed entrances, live travel times or market prices."
                if key == "editorial"
                else "Manually reviewed selected factual information from public official source/search result on 5 November 2026; linked for verification."
            ),
        )
    )

places = []


def place(pid, name, category, area, lat, lon, tags, duration, source, summary, hours=None):
    refs = {
        "identity": ["ev-" + source],
        "coordinates": ["ev-editorial"],
        "visit_duration": ["ev-editorial"],
    }
    if hours:
        refs["hours"] = ["ev-" + source]
    places.append(
        dict(
            id=pid,
            name=name,
            category=category,
            area=area,
            coordinates={"latitude": lat, "longitude": lon, "precision": "approximate"},
            interests=tags,
            visit_minutes_min=duration[0],
            visit_minutes_max=duration[1],
            accessibility="unknown",
            hours=hours,
            crowd_guidance=None,
            summary=summary,
            field_evidence=refs,
        )
    )


attractions = [
    (
        "al-fahidi",
        "Al Fahidi Historical Neighbourhood",
        "Bur Dubai",
        25.264,
        55.299,
        ["culture"],
        (60, 120),
        "culture",
        "Heritage district for a walking visit; individual venues require separate checks.",
    ),
    (
        "al-seef",
        "Al Seef waterfront",
        "Bur Dubai",
        25.265,
        55.309,
        ["culture", "waterfront"],
        (60, 120),
        "alseef",
        "Creek-side heritage-style district; shops and activities have separate conditions.",
    ),
    (
        "gold-souk",
        "Gold Souk",
        "Deira",
        25.286,
        55.297,
        ["culture", "shopping"],
        (45, 90),
        "culture",
        "Market visit option; purchases are discretionary and excluded from entry estimates.",
    ),
    (
        "textile-souk",
        "Textile Souk",
        "Bur Dubai",
        25.263,
        55.296,
        ["culture", "shopping"],
        (45, 75),
        "culture",
        "Textile market visit; check individual shop hours.",
    ),
    (
        "kite-beach",
        "Kite Beach",
        "Jumeirah",
        25.165,
        55.209,
        ["beach"],
        (90, 180),
        "kite",
        "Beach outing option; equipment, dining and safety conditions need separate checks.",
    ),
    (
        "jbr-beach",
        "The Beach at JBR",
        "Dubai Marina",
        25.078,
        55.134,
        ["beach"],
        (90, 180),
        "beaches",
        "Beachfront outing near Jumeirah Beach Residence.",
    ),
    (
        "marina-walk",
        "Dubai Marina waterfront",
        "Dubai Marina",
        25.081,
        55.145,
        ["waterfront"],
        (60, 120),
        "marina",
        "Marina exploration option; the centroid does not identify a walking entrance.",
    ),
    (
        "dubai-mall",
        "Dubai Mall",
        "Downtown",
        25.198,
        55.279,
        ["shopping"],
        (90, 180),
        "mall",
        "Shopping stop with separately ticketed attractions; store and attraction hours vary.",
    ),
    (
        "dubai-frame",
        "Dubai Frame",
        "Bur Dubai",
        25.235,
        55.301,
        ["architecture", "culture"],
        (60, 120),
        "frame",
        "Ticketed landmark; published standard fares are retained separately.",
    ),
    (
        "alserkal",
        "Alserkal Avenue",
        "Al Quoz",
        25.142,
        55.225,
        ["art", "culture"],
        (90, 150),
        "culture",
        "Arts district; entry is separate from priced exhibitions and activities.",
    ),
    (
        "shindagha",
        "Al Shindagha Museum",
        "Bur Dubai",
        25.269,
        55.290,
        ["culture"],
        (120, 180),
        "culture",
        "Museum candidate; a current applicable ticket and operating window need verification.",
    ),
    (
        "mbr-library",
        "Mohammed Bin Rashid Library",
        "Al Jaddaf",
        25.224,
        55.344,
        ["culture", "books"],
        (60, 120),
        "city-guide",
        "Library visit candidate; booking and visitor eligibility remain unverified.",
    ),
]
for row in attractions:
    pid, name, area, lat, lon, tags, duration, source, summary = row
    place(
        pid,
        name,
        "attraction",
        area,
        lat,
        lon,
        tags,
        duration,
        source,
        summary,
        "Published daily 08:00–21:00; verify date-specific changes before scheduling."
        if pid == "dubai-frame"
        else None,
    )
restaurants = [
    (
        "arabian-tea-house",
        "Arabian Tea House (Al Fahidi)",
        "Bur Dubai",
        25.264,
        55.300,
        "tea-house",
        "Emirati/Arabic dining candidate in Al Fahidi.",
    ),
    (
        "al-ustad",
        "Al Ustad Special Kabab",
        "Bur Dubai",
        25.259,
        55.299,
        "food-tour",
        "Kebab restaurant candidate near Al Fahidi.",
    ),
    (
        "al-khayma",
        "Al Khayma Heritage Restaurant",
        "Bur Dubai",
        25.264,
        55.300,
        "food-tour",
        "Heritage dining candidate in Al Fahidi.",
    ),
    (
        "ravi-satwa",
        "Ravi Restaurant (Satwa)",
        "Satwa",
        25.226,
        55.280,
        "satwa",
        "Satwa dining alternative; confirm current menu and branch details.",
    ),
    (
        "bu-qtair",
        "Bu Qtair",
        "Jumeirah",
        25.152,
        55.198,
        "buqtair",
        "Seafood restaurant candidate by the fishing harbour.",
    ),
    (
        "al-fanar",
        "Al Fanar Seafood Market (Al Seef)",
        "Bur Dubai",
        25.267,
        55.310,
        "alfanar",
        "Emirati seafood dining candidate at Al Seef.",
    ),
]
for pid, name, area, lat, lon, source, summary in restaurants:
    place(pid, name, "restaurant", area, lat, lon, ["food"], (45, 90), source, summary)
areas = [
    ("bur-dubai", "Bur Dubai", 25.257, 55.297, ["culture"]),
    ("deira", "Deira", 25.270, 55.322, ["culture", "shopping"]),
    ("al-barsha", "Al Barsha", 25.113, 55.201, ["shopping"]),
    ("downtown", "Downtown Dubai", 25.193, 55.275, ["architecture", "shopping"]),
    ("jumeirah", "Jumeirah", 25.192, 55.235, ["beach"]),
    ("dubai-marina", "Dubai Marina", 25.081, 55.145, ["beach", "waterfront"]),
]
accommodation = []
for pid, name, lat, lon, tags in areas:
    place(
        "area-" + pid,
        name,
        "area",
        name,
        lat,
        lon,
        tags,
        (30, 60),
        "neighborhoods",
        "Accommodation search area; no named hotel, occupancy or room availability is established.",
    )
    accommodation.append(
        dict(
            id="stay-" + pid,
            area_id="area-" + pid,
            name=name + " accommodation search",
            max_occupancy=None,
            price_id="price-stay-" + pid,
            availability="unknown",
            evidence_ids=["ev-neighborhoods"],
            notes="Choose a property and obtain a dated per-room quote including mandatory fees before asserting budget feasibility.",
        )
    )
prices = []


def price(
    pid,
    entity,
    unit,
    status="unknown",
    low=None,
    high=None,
    source="editorial",
    reason="No applicable current price verified; obtain a dated quote.",
    age=None,
    fees="unknown",
):
    prices.append(
        dict(
            id=pid,
            entity_id=entity,
            unit=unit,
            status=status,
            low=low,
            high=high,
            taxes_fees=fees,
            age_category=age,
            quote_date="2026-11-05" if status == "known" else None,
            evidence_ids=["ev-" + source],
            reason=reason,
        )
    )


for p in places:
    if p["category"] != "area" and p["id"] not in ("dubai-frame", "alserkal"):
        price(
            "price-" + p["id"],
            p["id"],
            "per_person_meal" if p["category"] == "restaurant" else "per_person",
        )
for a in accommodation:
    price(a["price_id"], a["id"], "per_room_night")
price(
    "price-frame-adult",
    "dubai-frame",
    "per_person",
    "known",
    "50",
    "50",
    "frame",
    "Published adult admission; recheck visit date, eligibility and any booking charges.",
    age="adult",
)
price(
    "price-frame-infant",
    "dubai-frame",
    "per_person",
    "known",
    "0",
    "0",
    "frame",
    "Published admission for children under 3; special eligibility must be confirmed.",
    age="0-2",
    fees="included",
)
price(
    "price-frame-child",
    "dubai-frame",
    "per_person",
    "known",
    "20",
    "20",
    "frame",
    "Published child admission, ages 3–12; recheck age eligibility.",
    age="3-12",
)
price(
    "price-alserkal-entry",
    "alserkal",
    "per_person",
    "known",
    "0",
    "0",
    "culture",
    "General district entry only; paid activities and purchases excluded.",
    fees="included",
)
tariffs = []
for tier, amount, condition in [
    ("one-zone", "3", "Silver nol, one zone"),
    ("two-zones", "5", "Silver nol, two adjacent zones"),
    ("many-zones", "7.50", "Silver nol, more than two zones"),
]:
    pid = "nol-" + tier
    tariffs.append(
        dict(
            id=pid,
            name=condition,
            conditions="Standard Silver card fare per eligible journey. Determine zone path and transfer eligibility separately; card purchase is not included. No departure schedule supplied.",
            evidence_ids=["ev-rta"],
        )
    )
    price(
        "price-" + pid,
        pid,
        "per_journey",
        "known",
        amount,
        amount,
        "rta",
        condition + "; avoid charging transfers as independent journeys without checking rules.",
        age="standard",
        fees="included",
    )

for e in evidence:
    if e["source_id"] == "rove-offer":
        e["applicable_from"], e["applicable_to"] = "2026-10-06", "2026-11-30"
        e["max_age_days"] = 7
        e["method"] = (
            "Official offer indexed text reviewed on 5 November 2026; direct fetch unavailable. Reconfirm with operator."
        )
for pid, name, area_id in [
    ("rove-marina", "Rove Dubai Marina", "area-dubai-marina"),
    ("rove-jbr", "Rove JBR", "area-dubai-marina"),
    ("rove-la-mer", "Rove La Mer Beach", "area-jumeirah"),
]:
    accommodation.append(
        dict(
            id=pid,
            area_id=area_id,
            name=name,
            max_occupancy=None,
            price_id="price-" + pid,
            availability="unknown",
            evidence_ids=["ev-rove-offer"],
            notes="Conditional breakfast promotion through 30 November 2026. Confirm occupancy and availability. Non-Dubai participating properties excluded.",
        )
    )
    prices.append(
        dict(
            id="price-" + pid,
            entity_id=pid,
            unit="per_room_night",
            status="known",
            low="399",
            high=None,
            basis="starting_from",
            taxes_fees="excluded",
            quote_date="2026-11-05",
            evidence_ids=["ev-rove-offer"],
            reason="Starting rate only, not a quote or upper bound. Excludes 10% service, 7% municipality, 5% VAT and AED 10 per room/night tourism fee. Confirm tax bases separately.",
        )
    )
for p in prices:
    if p["entity_id"] == "ravi-satwa":
        p.update(
            status="estimated",
            low="18",
            high="27",
            quote_date="2026-11-05",
            evidence_ids=["ev-ravi-menu"],
            reason="Selected vegetarian/chicken/mutton meal boxes listed at AED 18/22/27. Range only for those choices; confirm branch, portion suitability and taxes. Other dishes may exceed it.",
        )

for policy in policies:
    key = policy["id"]
    policy["allowed_fields"] = (
        FIELDS
        if key == "editorial"
        else ["evidence", "prices", "accommodation"]
        if key == "rove-offer"
        else ["evidence", "prices"]
        if key == "ravi-menu"
        else ["evidence", "prices", "tariffs"]
        if key == "rta"
        else ["evidence", "identity", "hours", "prices"]
        if key == "frame"
        else ["evidence", "identity", "accommodation"]
        if key == "neighborhoods"
        else ["evidence", "identity", "prices"]
        if key == "culture"
        else ["evidence", "identity"]
    )

by_id = {p["id"]: p for p in places}
routes = []
pairs = [
    ("al-fahidi", "arabian-tea-house", "walk"),
    ("al-fahidi", "al-khayma", "walk"),
    ("al-fahidi", "al-ustad", "walk"),
    ("al-fahidi", "textile-souk", "walk"),
    ("al-fahidi", "al-seef", "walk"),
    ("al-seef", "al-fanar", "walk"),
    ("kite-beach", "bu-qtair", "walk"),
    ("jbr-beach", "marina-walk", "walk"),
    ("area-bur-dubai", "al-fahidi", "taxi"),
    ("area-bur-dubai", "dubai-frame", "taxi"),
    ("area-bur-dubai", "kite-beach", "taxi"),
    ("area-bur-dubai", "jbr-beach", "taxi"),
    ("area-bur-dubai", "alserkal", "taxi"),
    ("area-deira", "gold-souk", "taxi"),
    ("area-al-barsha", "alserkal", "taxi"),
    ("dubai-frame", "dubai-mall", "taxi"),
    ("alserkal", "kite-beach", "taxi"),
    ("textile-souk", "shindagha", "walk"),
]
for origin, destination, mode in pairs:
    for a, b in [(origin, destination), (destination, origin)]:
        c1, c2 = by_id[a]["coordinates"], by_id[b]["coordinates"]
        lat1, lat2 = map(math.radians, [c1["latitude"], c2["latitude"]])
        dlat = lat2 - lat1
        dlon = math.radians(c2["longitude"] - c1["longitude"])
        km = (
            6371
            * 2
            * math.asin(
                min(
                    1,
                    math.sqrt(
                        math.sin(dlat / 2) ** 2
                        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
                    ),
                )
            )
        )
        speed = 4 if mode == "walk" else 25
        low = max(10, math.ceil(km * 1.5 / speed * 60))
        high = max(low + 15, math.ceil(low * 1.8))
        routes.append(
            dict(
                id=f"route-{a}-{b}-{mode}",
                origin_id=a,
                destination_id=b,
                mode=mode,
                duration_min=low,
                duration_max=high,
                status="estimated",
                evidence_ids=["ev-editorial"],
                method="Illustrative bound from approximate centroid great-circle distance × 1.5 / assumed "
                + str(speed)
                + " km/h; 10 minute minimum, upper=max(lower+15,lower×1.8). No route existence, crossing, accessibility, congestion or service verified.",
            )
        )
# Only original editorial allowances and a few atomic facts are retained; no page bodies.
for e in evidence:
    if e["source_id"] in ("frame", "ravi-menu"):
        e["method"] = (
            "Official page directly checked on 5 November 2026; selected numerical facts only. Exact retrieval time not retained."
        )
    elif e["source_id"] == "rta":
        e["method"] = (
            "Official RTA indexed fare table checked on 5 November 2026; direct page timed out."
        )
for r in routes:
    r["feasibility_supported"] = False
    r["includes_contingency"] = True
# Operational dates for hotel starting offers are retained explicitly with the price.
for p in prices:
    if p["entity_id"].startswith("rove-"):
        p["applicable_from"], p["applicable_to"] = "2026-10-06", "2026-11-30"
catalog = dict(
    schema_version="1.0",
    dataset_version=VERSION,
    evidence=evidence,
    places=places,
    accommodation=accommodation,
    prices=prices,
    routes=routes,
    tariffs=tariffs,
)
enrich(catalog, policies)
review(catalog, policies)
add_stay_quotes(catalog, policies)
complete_example(catalog, policies)
for filename, data in [
    ("data/curated/dubai-seed.json", catalog),
    ("config/provider_policies/sources.json", policies),
]:
    path = ROOT / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print({k: len(v) for k, v in catalog.items() if isinstance(v, list)})

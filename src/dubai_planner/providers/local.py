from datetime import date, datetime, timezone

from dubai_planner.services.evidence import price_usable
from dubai_planner.storage.catalog import Catalog

from .interfaces import ProviderResult


class LocalProvider:
    def __init__(self, catalog: Catalog, now=None):
        self.catalog = catalog.model_copy(deep=True)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._evidence = {e.id: e for e in self.catalog.evidence}

    def _result(self, data, refs, *, missing="empty", on_date=None):
        evidence = [self._evidence[key].model_copy(deep=True) for key in sorted(set(refs))]
        warnings = []
        for e in evidence:
            expired = (self._now() - e.retrieved_at).total_seconds() > e.max_age_days * 86400
            outside = on_date and (
                (e.applicable_from and on_date < e.applicable_from)
                or (e.applicable_to and on_date > e.applicable_to)
            )
            if expired or outside:
                e.quality = "stale"
                warnings.append(f"Recheck evidence {e.id}; age or travel date exceeds its validity")
        qualities = {e.quality for e in evidence}
        freshness = next(
            (
                q
                for q in ("conflicting", "unavailable", "stale", "estimated", "known")
                if q in qualities
            ),
            "unavailable",
        )
        present = data is not None and data != []
        if not present:
            warnings.append("No matching local evidence; do not assume zero price or travel time")
        return ProviderResult(
            status="ok" if present else missing,
            data=data,
            evidence=evidence,
            warnings=warnings,
            freshness=freshness,
            dataset_version=self.catalog.dataset_version,
        )

    def search_places(self, query="", *, category=None, area=None, interests=None, limit=20):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")
        rows = [
            p
            for p in self.catalog.places
            if query.casefold() in (p.name + " " + p.summary).casefold()
            and (category is None or p.category == category)
            and (area is None or p.area.casefold() == area.casefold())
            and (not interests or set(interests).intersection(p.interests))
        ][:limit]
        return self._result(
            rows, [ref for p in rows for refs in p.field_evidence.values() for ref in refs]
        )

    def get_place_details(self, entity_id):
        place = next((p for p in self.catalog.places if p.id == entity_id), None)
        return self._result(
            place, [r for refs in place.field_evidence.values() for r in refs] if place else []
        )

    def get_price(self, entity_id, on_date: date | None = None):
        rows = [p for p in self.catalog.prices if p.entity_id == entity_id]
        result = self._result(
            rows, [e for p in rows for e in p.evidence_ids], missing="unavailable", on_date=on_date
        )
        if rows and all(p.status == "unknown" for p in rows):
            result.status = "unavailable"
            result.warnings.append("Price is explicitly unknown; it is not free")
        if any(p.basis == "starting_from" for p in rows):
            result.warnings.append(
                "Starting-from offer has no upper bound and cannot establish budget compliance"
            )
        if any(p.stay_scope for p in rows):
            result.warnings.append(
                "Snapshot totals require the exact stay dates, rooms and travelers in stay_scope; availability is not reserved"
            )
        if on_date is None and rows:
            result.warnings.append(
                "Undated lookup: no date-specific price or availability guarantee"
            )
        if rows and not any(
            price_usable(p, self._evidence, on_date=on_date, now=self._now()) for p in rows
        ):
            result.status = "unavailable"
            result.warnings.append(
                "No price product has usable evidence for this date; records retained for inspection only"
            )
        return result

    def search_accommodation(self, area_id=None):
        rows = [a for a in self.catalog.accommodation if area_id is None or a.area_id == area_id]
        result = self._result(rows, [e for a in rows for e in a.evidence_ids])
        result.warnings.append(
            "Area recommendations only; no live inventory or confirmed room availability"
        )
        return result

    def route(self, origin_id, destination_id, mode, departure=None):
        if mode not in ("walk", "taxi", "transit", "abra"):
            return ProviderResult(status="unsupported", warnings=["Unsupported transport mode"])
        row = next(
            (
                r
                for r in self.catalog.routes
                if (r.origin_id, r.destination_id, r.mode) == (origin_id, destination_id, mode)
            ),
            None,
        )
        result = self._result(
            row,
            row.evidence_ids if row else [],
            missing="unavailable",
            on_date=departure.date() if departure else None,
        )
        if row:
            result.warnings.append(
                "Editorial duration range; not live traffic, transit service or accessibility proof"
            )
        return result

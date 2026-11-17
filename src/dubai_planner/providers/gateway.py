"""Single policy-gated local entry point; no HTTP clients or paid adapters."""

from dubai_planner.storage.repository import CatalogRepository

from .local import LocalProvider


class ProviderGateway:
    def __init__(self, repository: CatalogRepository):
        self.repository = repository

    def _provider(self):
        # Recheck current policy on each call; revocation takes effect immediately.
        return LocalProvider(self.repository.load())

    def search_places(self, query="", **filters):
        return self._provider().search_places(query, **filters)

    def get_place_details(self, entity_id):
        return self._provider().get_place_details(entity_id)

    def get_price(self, entity_id, on_date=None):
        return self._provider().get_price(entity_id, on_date)

    def search_accommodation(self, area_id=None):
        return self._provider().search_accommodation(area_id)

    def route(self, origin_id, destination_id, mode, departure=None):
        return self._provider().route(origin_id, destination_id, mode, departure)

"""Local, reviewed source registry; datasets cannot authorize their own sources."""

import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field

from dubai_planner.domain.base import Identifier, Model


class SourcePolicy(Model):
    id: Identifier
    owner: str
    url: str
    reviewed_on: date
    review_note: str
    approved: bool = False
    permitted_use: str
    attribution: str
    persistence: bool = False
    export: bool = False
    max_retention_days: int | None = Field(default=None, gt=0)
    allowed_fields: list[str] = Field(min_length=1)


class PolicyDenied(ValueError):
    pass


class PolicyRegistry:
    def __init__(self, policies: list[SourcePolicy]):
        self.policies = {p.id: p for p in policies}
        if len(self.policies) != len(policies):
            raise PolicyDenied("Duplicate source policy IDs")

    @classmethod
    def load(cls, path: Path):
        return cls(
            [SourcePolicy.model_validate(p) for p in json.loads(path.read_text(encoding="utf-8"))]
        )

    def require(self, source_id: str, field: str, operation: Literal["read", "persist", "export"]):
        policy = self.policies.get(source_id)
        if not policy or not policy.approved:
            raise PolicyDenied(f"Unreviewed source: {source_id}")
        if field not in policy.allowed_fields:
            raise PolicyDenied(f"Source {source_id} does not permit field {field}")
        if operation == "persist" and not policy.persistence:
            raise PolicyDenied(f"Persistence denied for {source_id}")
        if operation == "export" and not policy.export:
            raise PolicyDenied(f"Export denied for {source_id}")
        if operation == "persist" and policy.max_retention_days is not None:
            raise PolicyDenied(
                "Time-limited provider data cannot enter the permanent curated catalog"
            )
        return policy

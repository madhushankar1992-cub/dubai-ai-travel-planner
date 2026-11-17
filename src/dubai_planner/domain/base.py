from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid", validate_default=True, validate_assignment=True, hide_input_in_errors=True
    )


def decimal_input(value):
    if isinstance(value, (float, bool)):
        raise ValueError("Use Decimal, an integer, or a decimal string; never float/bool money")
    return value


Money = Annotated[Decimal, BeforeValidator(decimal_input), Field(ge=0, allow_inf_nan=False)]
Count = Annotated[int, Field(strict=True, ge=0)]
PositiveCount = Annotated[int, Field(strict=True, gt=0)]
Identifier = Annotated[str, Field(min_length=1, pattern=r"^[a-zA-Z0-9_.:-]+$")]


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Audit timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)

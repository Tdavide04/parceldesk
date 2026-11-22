"""Shipment tracking in canonical form, independent of the tracking service.

Statuses follow 17TRACK's main statuses, which are also a good general vocabulary. Unknown values from a
provider are kept as they come (`status_raw`) and mapped to `unknown`: the provider's enum is open.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, get_args

Status = Literal[
    "not_found", "info_received", "in_transit", "expired", "available_for_pickup",
    "out_for_delivery", "delivery_failure", "delivered", "exception", "unknown",
]
STATUSES: tuple[str, ...] = get_args(Status)
# a shipment in one of these needs no more polling unless the user reactivates it
FINAL_STATUSES = frozenset({"delivered", "expired"})

TRACKING_NUMBER = re.compile(r"[A-Za-z0-9-]{5,50}")


def normalize_number(number: str) -> str:
    """Upper-case, without spaces; raises ValueError for what no carrier accepts (5-50 letters, digits, '-')."""
    value = re.sub(r"\s+", "", number or "").upper()
    if not TRACKING_NUMBER.fullmatch(value):
        raise ValueError("a tracking number has 5 to 50 letters, digits or '-'")
    return value


@dataclass(frozen=True)
class TrackedNumber:
    """A tracking number and, when known, the provider's carrier code (None = let the provider detect it)."""

    number: str
    carrier: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "number", normalize_number(self.number))


@dataclass(frozen=True)
class Registration(TrackedNumber):
    """What to register: extra hints improve carrier detection and some carriers need them."""

    tag: str | None = None  # free text echoed back by the provider, at most 100 characters
    origin_country: str | None = None  # ISO 3166-1 alpha-2
    destination_country: str | None = None
    destination_postal_code: str | None = None
    lang: str | None = None  # language of event descriptions, e.g. "it"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.tag is not None and len(self.tag) > 100:
            raise ValueError("tag is at most 100 characters")
        for name in ("origin_country", "destination_country"):
            value = getattr(self, name)
            if value is not None and not re.fullmatch(r"[A-Z]{2}", value):
                raise ValueError(f"{name} must be an ISO 3166-1 alpha-2 code")


@dataclass(frozen=True)
class TrackingEvent:
    """One carrier scan. `time_utc` is None when the carrier gave no usable time."""

    description: str
    time_utc: datetime | None
    time_local: str | None = None  # the carrier's own time, offset included, as given
    location: str | None = None
    status: Status = "unknown"
    sub_status: str | None = None
    carrier_name: str | None = None


@dataclass(frozen=True)
class TrackingSnapshot:
    """Everything the provider knows about one number right now. Events are newest first."""

    number: str
    carrier: int | None
    status: Status
    status_raw: str | None
    sub_status: str | None
    sub_status_description: str | None
    events: list[TrackingEvent]
    # changes whenever any event changes: compare it to skip unchanged shipments
    events_hash: str | None
    delivered_at: datetime | None = None
    estimated_delivery_from: datetime | None = None
    estimated_delivery_to: datetime | None = None
    tag: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class Accepted:
    number: str
    carrier: int | None


@dataclass(frozen=True)
class RejectedNumber:
    number: str
    code: int | None
    message: str


@dataclass(frozen=True)
class BatchResult:
    """Batch calls can succeed for some numbers and fail for others."""

    accepted: list[Accepted] = field(default_factory=list)
    rejected: list[RejectedNumber] = field(default_factory=list)


@dataclass(frozen=True)
class TrackingResult:
    snapshots: list[TrackingSnapshot] = field(default_factory=list)
    rejected: list[RejectedNumber] = field(default_factory=list)


@dataclass(frozen=True)
class Quota:
    total: int
    used: int
    remaining: int

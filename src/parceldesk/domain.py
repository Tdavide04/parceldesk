"""Shipment tracking in canonical form, independent of the carrier.

Each carrier's own status text is kept as it comes (`status_raw`) and mapped to a canonical `Status`; text a
provider does not recognise maps to `unknown`, because carriers add new wordings without notice.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, get_args

Status = Literal[
    "not_found", "info_received", "in_transit", "expired", "available_for_pickup",
    "out_for_delivery", "delivery_failure", "delivered", "exception", "unknown",
]
STATUSES: tuple[str, ...] = get_args(Status)
# a shipment in one of these needs no more polling unless the user reactivates it. No carrier reports
# `expired`: the hub sets it when a shipment has had no update for too long.
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
    """A tracking number and the carrier that handles it (a provider's `carrier`, such as "poste")."""

    number: str
    carrier: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "number", normalize_number(self.number))
        if not self.carrier:
            raise ValueError("the carrier is required: see parceldesk.detect_carriers for hints")


@dataclass(frozen=True)
class TrackingEvent:
    """One carrier scan. `time_utc` is None when the carrier gave no usable time."""

    description: str
    time_utc: datetime | None
    time_local: str | None = None  # the carrier's own time, as given
    location: str | None = None
    status: Status = "unknown"


def events_hash(events: list[TrackingEvent]) -> str:
    """Changes whenever any event changes: the hub compares it to skip unchanged shipments."""
    rows = [
        [e.description, e.time_utc.isoformat() if e.time_utc else None, e.time_local, e.location, e.status]
        for e in events
    ]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class TrackingSnapshot:
    """Everything the carrier shows for one number right now. Events are newest first.

    A number the carrier does not know yet is a snapshot with status `not_found` and no events, not an error:
    carriers often show a shipment only hours after the label is printed.
    """

    number: str
    carrier: str
    status: Status
    status_raw: str | None
    events: list[TrackingEvent]
    delivered_at: datetime | None = None
    estimated_delivery: str | None = None  # as the carrier writes it: a date, a range or a sentence
    raw_payload: Any = field(default=None, repr=False)
    events_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "events_hash", events_hash(self.events))


@dataclass(frozen=True)
class RejectedNumber:
    """A number nobody could answer for. `retryable` is True when trying again later may work."""

    number: str
    carrier: str
    reason: str
    retryable: bool


@dataclass(frozen=True)
class TrackingResult:
    """Calls can succeed for some numbers and fail for others: always check `rejected`."""

    snapshots: list[TrackingSnapshot] = field(default_factory=list)
    rejected: list[RejectedNumber] = field(default_factory=list)

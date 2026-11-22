"""Shipment tracking for Personal Collection Hub: canonical domain types, a provider port and a 17TRACK client."""
from parceldesk.domain import (
    FINAL_STATUSES,
    STATUSES,
    Accepted,
    BatchResult,
    Quota,
    Registration,
    RejectedNumber,
    Status,
    TrackedNumber,
    TrackingEvent,
    TrackingResult,
    TrackingSnapshot,
    normalize_number,
)
from parceldesk.provider import PermanentTrackingError, TrackingProvider, TransientTrackingError
from parceldesk.seventeentrack import SeventeenTrack, parse_snapshot

__version__ = "0.1.0"

__all__ = [
    "FINAL_STATUSES", "STATUSES", "Accepted", "BatchResult", "PermanentTrackingError", "Quota", "Registration",
    "RejectedNumber", "SeventeenTrack", "Status", "TrackedNumber", "TrackingEvent", "TrackingProvider", "TrackingResult",
    "TrackingSnapshot", "TransientTrackingError", "normalize_number", "parse_snapshot",
]

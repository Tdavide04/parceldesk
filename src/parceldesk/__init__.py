"""Shipment tracking for Personal Collection Hub: canonical domain types, a per-carrier provider port and the desk."""
from parceldesk.desk import NUMBER_FORMATS, ParcelDesk, detect_carriers
from parceldesk.domain import (
    FINAL_STATUSES,
    STATUSES,
    RejectedNumber,
    Status,
    TrackedNumber,
    TrackingEvent,
    TrackingResult,
    TrackingSnapshot,
    events_hash,
    normalize_number,
)
from parceldesk.http import CarrierHttp
from parceldesk.provider import PermanentTrackingError, TrackingProvider, TransientTrackingError

__version__ = "0.2.0"

__all__ = [
    "FINAL_STATUSES", "NUMBER_FORMATS", "STATUSES", "CarrierHttp", "ParcelDesk", "PermanentTrackingError",
    "RejectedNumber", "Status", "TrackedNumber", "TrackingEvent", "TrackingProvider", "TrackingResult",
    "TrackingSnapshot", "TransientTrackingError", "detect_carriers", "events_hash", "normalize_number",
]

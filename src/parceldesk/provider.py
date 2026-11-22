"""The port between ParcelDesk and one carrier's tracking pages, and the errors a provider may raise."""
from typing import Protocol

from parceldesk.domain import TrackingSnapshot


class TransientTrackingError(Exception):
    """Worth retrying later: network, timeout, 5xx, 429 once the HTTP client's own retries are exhausted."""


class PermanentTrackingError(Exception):
    """Retrying will not help until the code changes: access refused, or the page no longer has the shape we parse."""


class TrackingProvider(Protocol):
    """Reads one carrier's public tracking (hub ADR-0010: polling). Translates only: no persistence or scheduling.

    `track` receives at most `max_batch` normalised numbers and returns one snapshot per number, in any order.
    It raises TransientTrackingError or PermanentTrackingError when it cannot answer for the whole batch.
    """

    carrier: str
    max_batch: int

    def track(self, numbers: list[str]) -> list[TrackingSnapshot]:
        ...
